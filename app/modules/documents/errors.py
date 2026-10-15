from app.shared.errors import AppError, Conflict, Invalid, NotFound


class NotPdf(Invalid):
    code, error_code = "not_pdf", "DOC_001"


class FileTooLarge(Invalid):
    code, error_code = "file_too_large", "DOC_002"


class TooManyFiles(Invalid):
    code, error_code = "too_many_files", "DOC_003"


class PdfUnreadable(Invalid):
    code, error_code = "pdf_unreadable", "DOC_004"


class DocumentNotFound(NotFound):
    code, error_code = "document_not_found", "DOC_007"


class ProcessingTimeout(Invalid):
    code, error_code = "processing_timeout", "DOC_006"


class PageNotFound(NotFound):
    code, error_code = "page_not_found", "DOC_008"


class PageOutOfRange(Invalid):
    code, error_code = "page_out_of_range", "DOC_009"


class NoDefaultPreset(Conflict):
    code, error_code = "no_default_preset", "DOC_012"


class OcrPresetNotFound(NotFound):
    code, error_code = "ocr_preset_not_found", "DOC_013"


class PageRenderFailed(AppError):
    # The page was parsed at upload; failing to rasterise it is a server fault.
    status, code, error_code = 500, "internal_error", "SYS_002"
