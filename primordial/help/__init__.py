"""In-app help document loading and search helpers."""

from .document_model import (
    HelpDocument,
    HelpSection,
    SearchResult,
    bundled_predator_prey_guide_path,
    load_help_document,
    parse_markdown_document,
    search_sections,
)

__all__ = [
    "HelpDocument",
    "HelpSection",
    "SearchResult",
    "bundled_predator_prey_guide_path",
    "load_help_document",
    "parse_markdown_document",
    "search_sections",
]
