from app.shared.errors import Invalid, NotFound


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
