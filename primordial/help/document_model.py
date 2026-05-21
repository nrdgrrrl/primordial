"""Small Markdown-backed document model for the in-app help browser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from primordial.utils.paths import get_base_path


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")


@dataclass(frozen=True)
class HelpSection:
    """One navigable section parsed from a Markdown document."""

    title: str
    level: int
    body: str


@dataclass(frozen=True)
class SearchResult:
    """A section match for a simple case-insensitive help search."""

    section_index: int
    title: str
    snippet: str


@dataclass(frozen=True)
class HelpDocument:
    """Parsed help document plus source/error metadata."""

    title: str
    sections: tuple[HelpSection, ...]
    source_path: Path
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class HelpDocEntry:
    """One registered help document in the in-app browser."""

    doc_id: str
    title: str
    description: str
    rel_path: str

    def resolve_path(self) -> Path:
        return get_base_path() / self.rel_path


HELP_DOCUMENTS: tuple[HelpDocEntry, ...] = (
    HelpDocEntry(
        doc_id="quick_start",
        title="Start",
        description="What Primordial is, what you see on screen, basic controls, and how to read the HUD.",
        rel_path="docs/help_quick_start.md",
    ),
    HelpDocEntry(
        doc_id="organisms",
        title="Organisms",
        description="What organisms are, how genomes drive behavior and appearance, reproduction, mutation, lineages, and evolution.",
        rel_path="docs/help_organisms.md",
    ),
    HelpDocEntry(
        doc_id="reading_creatures",
        title="Reading",
        description="How to read creature appearance, what is hidden, limits of visual inference, and how to watch evolution happen.",
        rel_path="docs/help_reading_creatures.md",
    ),
    HelpDocEntry(
        doc_id="predator_prey",
        title="Predator-Prey",
        description="How predators and prey behave, depth bands, scarcity, food cycles, game over, and adaptive tuning.",
        rel_path="docs/help_predator_prey.md",
    ),
    HelpDocEntry(
        doc_id="controls_settings",
        title="Controls",
        description="Runtime controls, settings guide, tutorial, save/load, other modes, and glossary.",
        rel_path="docs/help_controls_settings.md",
    ),
)

HELP_DOC_BY_ID: dict[str, HelpDocEntry] = {entry.doc_id: entry for entry in HELP_DOCUMENTS}

DEFAULT_HELP_DOC_ID = "quick_start"


def load_help_document_by_id(doc_id: str) -> HelpDocument:
    """Load a registered help document by its doc_id. Falls back to error document."""
    entry = HELP_DOC_BY_ID.get(doc_id)
    if entry is None:
        return HelpDocument(
            title="Unknown Document",
            sections=(
                HelpSection(
                    title="Unknown Document",
                    level=1,
                    body=f"No help document registered with id {doc_id!r}.",
                ),
            ),
            source_path=Path(f"<unknown:{doc_id}>"),
            error=f"unknown doc_id: {doc_id}",
        )
    return load_help_document(entry.resolve_path())


def bundled_help_doc_path(doc_id: str = DEFAULT_HELP_DOC_ID) -> Path:
    """Resolve the path for a registered help document."""
    entry = HELP_DOC_BY_ID.get(doc_id)
    if entry is not None:
        return entry.resolve_path()
    return get_base_path() / "docs" / "help_quick_start.md"


def load_help_document(path: Path | None = None) -> HelpDocument:
    """Load and parse a Markdown help document, returning an error document on failure."""
    source_path = path or bundled_help_doc_path()
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return HelpDocument(
            title="Documentation Unavailable",
            sections=(
                HelpSection(
                    title="Documentation Unavailable",
                    level=1,
                    body=(
                        "Primordial could not load the bundled guide. "
                        f"Expected file: {source_path}"
                    ),
                ),
            ),
            source_path=source_path,
            error=str(exc),
        )
    document = parse_markdown_document(text, source_path=source_path)
    if not document.sections:
        return HelpDocument(
            title=document.title,
            sections=(
                HelpSection(
                    title="Empty Documentation",
                    level=1,
                    body="The bundled guide file exists, but it does not contain readable help content.",
                ),
            ),
            source_path=source_path,
            error="empty document",
        )
    return document


def parse_markdown_document(text: str, *, source_path: Path | None = None) -> HelpDocument:
    """Parse Markdown into flat heading sections without implementing full Markdown."""
    source = source_path or Path("<memory>")
    sections: list[HelpSection] = []
    current_title: str | None = None
    current_level = 1
    current_lines: list[str] = []
    document_title = source.stem.replace("_", " ").title()

    def flush() -> None:
        nonlocal current_title, current_lines, current_level, document_title
        if current_title is None:
            body = _clean_body("\n".join(current_lines))
            if body:
                sections.append(HelpSection("Overview", 1, body))
                if document_title == source.stem.replace("_", " ").title():
                    document_title = "Overview"
            current_lines = []
            return
        body = _clean_body("\n".join(current_lines))
        sections.append(HelpSection(current_title, current_level, body))
        if len(sections) == 1:
            document_title = current_title
        current_lines = []

    for raw_line in text.splitlines():
        heading = _HEADING_RE.match(raw_line)
        if heading:
            flush()
            current_level = len(heading.group(1))
            current_title = _clean_inline(heading.group(2).strip())
            continue
        current_lines.append(raw_line)

    flush()
    return HelpDocument(
        title=document_title,
        sections=tuple(sections),
        source_path=source,
    )


def search_sections(sections: tuple[HelpSection, ...] | list[HelpSection], query: str) -> list[SearchResult]:
    """Search section titles and body text with simple case-insensitive matching."""
    needle = query.strip().casefold()
    if not needle:
        return []
    results: list[SearchResult] = []
    for index, section in enumerate(sections):
        title = section.title
        body = section.body
        title_match = needle in title.casefold()
        body_index = body.casefold().find(needle)
        if not title_match and body_index < 0:
            continue
        snippet = title
        if body_index >= 0:
            snippet = _snippet_for_match(body, body_index, len(needle))
        results.append(SearchResult(index, title, snippet))
    return results


def _clean_body(text: str) -> str:
    lines = [_clean_block_line(line.rstrip()) for line in text.strip().splitlines()]
    cleaned: list[str] = []
    blank_pending = False
    for line in lines:
        if not line:
            blank_pending = bool(cleaned)
            continue
        if blank_pending and cleaned:
            cleaned.append("")
        cleaned.append(line)
        blank_pending = False
    return "\n".join(cleaned).strip()


def _clean_block_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            return ""
        return " | ".join(cell for cell in cells if cell)
    return _clean_inline(stripped)


def _clean_inline(text: str) -> str:
    text = _LINK_RE.sub(r"\1 (\2)", text)
    return _EMPHASIS_RE.sub("", text)


def _snippet_for_match(text: str, start: int, length: int) -> str:
    snippet_start = max(0, start - 48)
    snippet_end = min(len(text), start + length + 72)
    snippet = " ".join(text[snippet_start:snippet_end].split())
    if snippet_start > 0:
        snippet = "... " + snippet
    if snippet_end < len(text):
        snippet += " ..."
    return snippet
