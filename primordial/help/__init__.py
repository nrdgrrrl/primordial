"""In-app help document loading and search helpers."""

from .document_model import (
    DEFAULT_HELP_DOC_ID,
    HELP_DOC_BY_ID,
    HELP_DOCUMENTS,
    HelpDocEntry,
    HelpDocument,
    HelpSection,
    SearchResult,
    bundled_primordial_guide_path,
    load_help_document,
    load_help_document_by_id,
    parse_markdown_document,
    search_sections,
)

__all__ = [
    "DEFAULT_HELP_DOC_ID",
    "HELP_DOC_BY_ID",
    "HELP_DOCUMENTS",
    "HelpDocEntry",
    "HelpDocument",
    "HelpSection",
    "SearchResult",
    "bundled_primordial_guide_path",
    "load_help_document",
    "load_help_document_by_id",
    "parse_markdown_document",
    "search_sections",
]
