from typing import Protocol

from .request import RepairExtractedTextRequest


class RepairExtractedTextInputBoundary(Protocol):
    def execute(self, request: RepairExtractedTextRequest) -> None:
        """Propose repairs for one flagged parser page, without changing extraction.

        Resolve caller-supplied preset_name against the administrator-approved
        vision catalogue; unknown name emits invalid_preset without source/model I/O.
        Caller cannot supply an endpoint/model/key or trigger silent substitution.
        Load authoritative page facts for the requested document and page.
        A page whose extraction method is vision is ineligible, even if vision
        failed or its retained raw parser report is flagged. No LLM call for it.
        An unassessed page is not equivalent to an assessed, unflagged page.
        Eligible pages send exact raw text and every original signal span together
        in one repair invocation. Never apply raw offsets to vision text.
        Suggestions do not overwrite or persist a modified extraction result.
        The trusted caller must authorize document access before invoking this
        boundary; user-supplied identity/permissions are not authorization.
        Emit one semantic outcome through Output Boundary on normal completion.
        Append validated Suggested/NoChanges/Unrepairable to RepairRunRepository
        before presentation; include the acknowledged repair_id in that outcome.
        Never store rejected requests or invalid proposals. History is immutable;
        offsets reference the saved extraction snapshot, not an updated document.
        Storage failure propagates with no success or retry. A failed acknowledgement
        may follow publication; presentation failure cannot roll back the record
        or the prior model call. There is no transaction spanning model and storage.

        Proposed edits may expand beyond a signal span but must overlap at least
        one signal and must not overlap each other. Structural validity is not
        evidence that an LLM correction is accurate.
        NoChanges and Unrepairable are separate expected outcomes; neither
        certifies source correctness. System outages are not Unrepairable.
        Inject ModelPresetCatalogue from the SAME trusted catalogue used by vision;
        TextRepairer receives the exact selected VisionPreset including its required
        nonblank string api_key from trusted JSON. Validate every preset before I/O;
        no environment fallback. Outcomes/history contain approved preset name/model,
        never the endpoint or key. Do not log/serialize trusted config or credentials.
        Malformed trusted catalogue, including missing/invalid key ->
        InvalidModelPresetCatalogue -> outer handler without source/model/history I/O.
        Ports name RepairSourceError/TextRepairError/RepairRunStorageError for known system failures;
        these reach the outer handler without retry or success presentation.
        Misbound source facts or malformed model proposals are contract failures:
        InvalidRepairSourceResult/InvalidTextRepairResult -> outer handler, not
        expected rejection or Unrepairable. No success on failure.
        Local CLI composition supplies real JSON adapters, an OpenAI-compatible
        client using preset.api_key and a summary-only Presenter. The shared JSON
        loader requires a bounded owner-only regular file, rejects final symlinks
        and duplicate keys, and never reads API credentials from the environment.
        Authorization is OS-user/private-file based; a multi-user authenticated
        controller remains outside this slice.
        Real provider compatibility/capability is not proved by local HTTP tests.
        """
        ...
