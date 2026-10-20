from dataclasses import replace

from ....domain.documents.extraction import PageExtraction
from ....domain.documents.text_quality import RawPageQuality
from ....domain.documents.text_repairs import (
    PageRepairSuggestions, RepairEditCandidate, RepairSourceText,
)
from ...model_presets import ModelPresetCatalogue, UnknownVisionPreset
from .errors import (
    InvalidRepairSourceResult, InvalidTextRepairResult, OutsideSignalsDiagnostic,
    PROPOSAL_DIAGNOSTIC_RANGE_LIMIT,
)
from .input_boundary import RepairExtractedTextInputBoundary
from .output_boundary import RepairExtractedTextOutputBoundary
from .ports import (
    LoadedRepairPage, RepairPageNotFound, RepairPageSource, RepairRunRepository, TextRepairer,
    TextRepairNoChanges, TextRepairProposal, TextRepairUnrepairable,
)
from .request import RepairExtractedTextRequest
from .response import (
    CompletedTextRepair, RepairNoChanges, RepairRejected, RepairSuggested,
    RepairUnrepairable, SuggestedTextRepair,
)


class RepairExtractedTextInteractor(RepairExtractedTextInputBoundary):
    def __init__(
        self, *, source: RepairPageSource, repairer: TextRepairer,
        output: RepairExtractedTextOutputBoundary, catalogue: ModelPresetCatalogue,
        repository: RepairRunRepository,
    ) -> None:
        self.repository = repository
        self.catalogue = catalogue
        self.source = source
        self.repairer = repairer
        self.output = output

    def execute(self, request: RepairExtractedTextRequest) -> None:
        preset = self.catalogue.select(request.preset_name)
        if isinstance(preset, UnknownVisionPreset):
            self.output.present(RepairRejected("invalid_preset"))
            return
        if (
            not isinstance(request.document_id, str) or not request.document_id.strip()
            or type(request.page_number) is not int or request.page_number < 1
        ):
            self.output.present(RepairRejected("invalid_request"))
            return
        loaded = self.source.load_page(
            document_id=request.document_id, page_number=request.page_number,
        )
        if isinstance(loaded, RepairPageNotFound):
            self.output.present(RepairRejected("page_not_found"))
            return
        if (
            not isinstance(loaded, LoadedRepairPage)
            or loaded.document_id != request.document_id
            or not isinstance(loaded.page, PageExtraction)
            or type(loaded.page.number) is not int or loaded.page.number != request.page_number
            or loaded.page.status not in ("extracted", "failed")
            or loaded.page.method not in ("pdf_text", "vision")
            or (loaded.page.method == "pdf_text" and loaded.page.status != "extracted")
        ):
            raise InvalidRepairSourceResult("Invalid or misbound extraction snapshot")
        if loaded.page.method == "vision":
            self.output.present(RepairRejected("vision_page"))
            return
        if loaded.raw_quality is None:
            self.output.present(RepairRejected("not_assessed"))
            return
        if (
            not isinstance(loaded.raw_quality, RawPageQuality)
            or type(loaded.raw_quality.number) is not int
            or loaded.raw_quality.number != request.page_number
            or loaded.raw_quality.raw_text != loaded.page.text
            or type(loaded.raw_quality.flagged) is not bool
        ):
            raise InvalidRepairSourceResult("Incoherent raw source report")
        if not loaded.raw_quality.flagged:
            self.output.present(RepairRejected("page_not_flagged"))
            return
        repair_source = RepairSourceText.create(
            raw_text=loaded.raw_quality.raw_text, spans=loaded.raw_quality.spans,
        )
        if not isinstance(repair_source, RepairSourceText):
            raise InvalidRepairSourceResult("Invalid raw repair source")
        result = self.repairer.propose(
            raw_text=repair_source.raw_text, spans=repair_source.spans, preset=preset,
        )
        if isinstance(result, TextRepairNoChanges):
            self._record_and_present(RepairNoChanges(
                request.document_id, request.page_number, preset.name, preset.model,
            ))
            return
        if isinstance(result, TextRepairUnrepairable):
            self._record_and_present(RepairUnrepairable(
                request.document_id, request.page_number, preset.name, preset.model,
            ))
            return
        if isinstance(result, TextRepairProposal):
            if not isinstance(result.edits, tuple) or any(
                not isinstance(edit, SuggestedTextRepair) for edit in result.edits
            ):
                raise InvalidTextRepairResult("Malformed model edit facts")
            proposal = PageRepairSuggestions.create(
                source=repair_source,
                edits=tuple(RepairEditCandidate(edit.start, edit.end, edit.replacement)
                            for edit in result.edits),
            )
            if not isinstance(proposal, PageRepairSuggestions):
                diagnostic = None
                if proposal.reason == "outside_signals":
                    diagnostic = OutsideSignalsDiagnostic(
                        edit_count=len(result.edits),
                        outside_signal_edit_count=len(proposal.outside_signal_edit_indices),
                        signal_count=len(repair_source.spans),
                        outside_signal_edit_ranges=tuple(
                            (result.edits[index].start, result.edits[index].end)
                            for index in proposal.outside_signal_edit_indices[:PROPOSAL_DIAGNOSTIC_RANGE_LIMIT]
                        ),
                        signal_ranges=tuple(
                            (span.start, span.end)
                            for span in repair_source.spans[:PROPOSAL_DIAGNOSTIC_RANGE_LIMIT]
                        ),
                    )
                raise InvalidTextRepairResult(
                    "Invalid model repair proposal", reason=proposal.reason,
                    proposal_diagnostic=diagnostic,
                )
            self._record_and_present(RepairSuggested(
                request.document_id, request.page_number,
                tuple(SuggestedTextRepair(edit.start, edit.end, edit.replacement)
                      for edit in proposal.edits),
                preset.name, preset.model,
            ))
            return
        raise InvalidTextRepairResult("Undeclared model repair result")

    def _record_and_present(self, result: CompletedTextRepair) -> None:
        saved = self.repository.save(result)
        self.output.present(replace(result, repair_id=saved.repair_id))
