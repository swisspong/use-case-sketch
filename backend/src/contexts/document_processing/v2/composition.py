"""Local CLI composition: real JSON storage, parser, and opt-in remote text repair.

Vision fallback remains deliberately unavailable. Repair dependencies and output
state are created per execution; no shared Presenter or network connection.
"""

from pathlib import Path
from typing import Literal

from .application.use_cases.extract_pdf_text.configuration import ExtractionConfig
from .application.use_cases.extract_pdf_text.input_boundary import ExtractPdfTextInputBoundary
from .application.use_cases.extract_pdf_text.interactor import ExtractPdfTextInteractor
from .application.use_cases.extract_pdf_text.output_boundary import ExtractPdfTextOutputBoundary
from .infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from .infrastructure.pypdf_text_extractor import PypdfTextExtractor
from .infrastructure.unavailable_fallback_extractor import UnavailableFallbackExtractor
from .application.model_presets import ModelPresetCatalogue
from .application.use_cases.repair_extracted_text.input_boundary import RepairExtractedTextInputBoundary
from .application.use_cases.repair_extracted_text.interactor import RepairExtractedTextInteractor
from .application.use_cases.repair_extracted_text.output_boundary import RepairExtractedTextOutputBoundary
from .infrastructure.local_json_repair_page_source import LocalJsonRepairPageSource
from .infrastructure.local_json_repair_run_repository import LocalJsonRepairRunRepository
from .infrastructure.local_json_repair_failure_log import LocalJsonRepairFailureLog
from .infrastructure.openai_compatible_text_repairer import OpenAICompatibleTextRepairer


def build_local_extraction(
    *, config: ExtractionConfig, data_dir: Path, output: ExtractPdfTextOutputBoundary,
) -> ExtractPdfTextInputBoundary:
    return ExtractPdfTextInteractor(
        pdf_extractor=PypdfTextExtractor(), fallback=UnavailableFallbackExtractor(),
        store=LocalJsonExtractionStore(data_dir), output=output, config=config,
    )


def build_local_text_repair(
    *, catalogue: ModelPresetCatalogue, data_dir: Path,
    output: RepairExtractedTextOutputBoundary,
    timeout_seconds: float = 30, max_tokens: int = 2048,
    reasoning_effort: Literal["low"] | None = None,
) -> RepairExtractedTextInputBoundary:
    return RepairExtractedTextInteractor(
        source=LocalJsonRepairPageSource(data_dir),
        repairer=OpenAICompatibleTextRepairer(
            timeout_seconds=timeout_seconds, max_tokens=max_tokens, reasoning_effort=reasoning_effort,
        ),
        repository=LocalJsonRepairRunRepository(data_dir), output=output, catalogue=catalogue,
    )


def build_local_repair_failure_log(*, log_dir: Path) -> LocalJsonRepairFailureLog:
    """Outer-handler logging only; never an Interactor dependency."""
    return LocalJsonRepairFailureLog(log_dir)
