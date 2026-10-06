"""Local CLI composition: real parser/store and deliberately unavailable vision."""

from pathlib import Path

from .application.use_cases.extract_pdf_text.configuration import ExtractionConfig
from .application.use_cases.extract_pdf_text.input_boundary import ExtractPdfTextInputBoundary
from .application.use_cases.extract_pdf_text.interactor import ExtractPdfTextInteractor
from .application.use_cases.extract_pdf_text.output_boundary import ExtractPdfTextOutputBoundary
from .infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from .infrastructure.pypdf_text_extractor import PypdfTextExtractor
from .infrastructure.unavailable_fallback_extractor import UnavailableFallbackExtractor


def build_local_extraction(
    *, config: ExtractionConfig, data_dir: Path, output: ExtractPdfTextOutputBoundary,
) -> ExtractPdfTextInputBoundary:
    return ExtractPdfTextInteractor(
        pdf_extractor=PypdfTextExtractor(), fallback=UnavailableFallbackExtractor(),
        store=LocalJsonExtractionStore(data_dir), output=output, config=config,
    )
