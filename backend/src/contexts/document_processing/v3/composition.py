"""v3 CLI compositions with real local JSON storage.

Extraction calls no model or network; it only suggests OCR. OCR is a separate,
user-triggered use case. Output state is created per execution; no shared Presenter.
"""

from pathlib import Path

from .application.use_cases.extract_pdf_text.configuration import ExtractionConfig
from .application.use_cases.extract_pdf_text.input_boundary import ExtractPdfTextInputBoundary
from .application.use_cases.extract_pdf_text.interactor import ExtractPdfTextInteractor
from .application.use_cases.extract_pdf_text.output_boundary import ExtractPdfTextOutputBoundary
from .application.use_cases.ocr_document_pages.configuration import OcrConfig
from .application.use_cases.ocr_document_pages.input_boundary import OcrDocumentPagesInputBoundary
from .application.use_cases.ocr_document_pages.interactor import OcrDocumentPagesInteractor
from .application.use_cases.ocr_document_pages.output_boundary import OcrDocumentPagesOutputBoundary
from .infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from .infrastructure.local_json_ocr_attempt_store import LocalJsonOcrAttemptStore
from .infrastructure.local_json_saved_document_source import LocalJsonSavedDocumentSource
from .infrastructure.openai_compatible_ocr_reader import OpenAICompatibleOcrReader
from .infrastructure.pypdf_text_extractor import PypdfTextExtractor
from .infrastructure.pypdfium2_page_renderer import Pypdfium2PageRenderer


def build_local_extraction(
    *, config: ExtractionConfig, data_dir: Path, output: ExtractPdfTextOutputBoundary,
) -> ExtractPdfTextInputBoundary:
    return ExtractPdfTextInteractor(
        pdf_extractor=PypdfTextExtractor(), store=LocalJsonExtractionStore(data_dir),
        output=output, config=config,
    )


def build_local_ocr(
    *, config: OcrConfig, data_dir: Path, output: OcrDocumentPagesOutputBoundary,
) -> OcrDocumentPagesInputBoundary:
    """User-triggered OCR: real local files, PDFium renderer, OpenAI-compatible HTTP client.

    New adapters per execution; the caller supplies a per-execution Presenter.
    """
    return OcrDocumentPagesInteractor(
        documents=LocalJsonSavedDocumentSource(data_dir), renderer=Pypdfium2PageRenderer(),
        ocr=OpenAICompatibleOcrReader(), attempts=LocalJsonOcrAttemptStore(data_dir),
        output=output, config=config,
    )
