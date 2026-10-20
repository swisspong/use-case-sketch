from dataclasses import dataclass


@dataclass(frozen=True)
class RepairExtractedTextRequest:
    """Select a saved document's one-based page, not caller-supplied source facts.

    The trusted caller is responsible for authenticated resource access.
    Caller selects an approved preset by name, from the vision catalogue.
    Flag, raw text, spans, endpoint, model and permissions are not request fields.
    """

    document_id: str
    page_number: int
    preset_name: str
