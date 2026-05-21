from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.help import (
    DEFAULT_HELP_DOC_ID,
    HELP_DOC_BY_ID,
    HELP_DOCUMENTS,
    HelpDocument,
    HelpDocEntry,
    HelpSection,
    bundled_help_doc_path,
    load_help_document,
    load_help_document_by_id,
    parse_markdown_document,
    search_sections,
)
from primordial.rendering.help_layout import calculate_help_layout
from primordial.rendering.help_navigation import HelpNavigation
from primordial.rendering.help_overlay import HelpOverlay


class HelpDocumentModelTests(unittest.TestCase):
    def test_parser_splits_headings_and_preserves_body(self) -> None:
        document = parse_markdown_document(
            "# Primordial Guide\n\nIntro text.\n\n## Food Cycle\n\n- Feast\n- Famine\n",
            source_path=Path("guide.md"),
        )

        self.assertEqual(document.title, "Primordial Guide")
        self.assertEqual([section.title for section in document.sections], ["Primordial Guide", "Food Cycle"])
        self.assertIn("Intro text.", document.sections[0].body)
        self.assertIn("- Feast", document.sections[1].body)

    def test_parser_handles_content_before_first_heading(self) -> None:
        document = parse_markdown_document(
            "Before heading.\n\n## First Heading\n\nBody.",
            source_path=Path("guide.md"),
        )

        self.assertEqual(document.sections[0].title, "Overview")
        self.assertEqual(document.sections[0].body, "Before heading.")
        self.assertEqual(document.sections[1].title, "First Heading")

    def test_load_missing_file_returns_error_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.md"

            document = load_help_document(missing_path)

        self.assertFalse(document.ok)
        self.assertEqual(document.sections[0].title, "Documentation Unavailable")

    def test_load_empty_file_returns_readable_empty_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_path = Path(temp_dir) / "empty.md"
            empty_path.write_text("", encoding="utf-8")

            document = load_help_document(empty_path)

        self.assertFalse(document.ok)
        self.assertEqual(document.sections[0].title, "Empty Documentation")

    def test_search_matches_titles_and_body_case_insensitively(self) -> None:
        sections = (
            HelpSection("Food Cycle", 2, "Feast and famine waves."),
            HelpSection("Depth Bands", 2, "Predators can miss across bands."),
        )

        title_results = search_sections(sections, "food")
        body_results = search_sections(sections, "MISS")
        no_results = search_sections(sections, "lineage")

        self.assertEqual([result.section_index for result in title_results], [0])
        self.assertEqual([result.section_index for result in body_results], [1])
        self.assertEqual(no_results, [])


class HelpDocumentRegistryTests(unittest.TestCase):
    def test_registry_has_multiple_documents(self) -> None:
        self.assertGreaterEqual(len(HELP_DOCUMENTS), 5)

    def test_quick_start_in_registry(self) -> None:
        self.assertIn("quick_start", HELP_DOC_BY_ID)

    def test_organisms_in_registry(self) -> None:
        self.assertIn("organisms", HELP_DOC_BY_ID)

    def test_reading_creatures_in_registry(self) -> None:
        self.assertIn("reading_creatures", HELP_DOC_BY_ID)

    def test_predator_prey_in_registry(self) -> None:
        self.assertIn("predator_prey", HELP_DOC_BY_ID)

    def test_controls_settings_in_registry(self) -> None:
        self.assertIn("controls_settings", HELP_DOC_BY_ID)

    def test_all_registered_docs_resolve_to_existing_files(self) -> None:
        for entry in HELP_DOCUMENTS:
            path = entry.resolve_path()
            self.assertTrue(
                path.exists(),
                f"Registered help doc {entry.doc_id!r} path does not exist: {path}",
            )

    def test_all_registered_docs_load_successfully(self) -> None:
        for entry in HELP_DOCUMENTS:
            doc = load_help_document_by_id(entry.doc_id)
            self.assertTrue(
                doc.ok,
                f"Registered help doc {entry.doc_id!r} failed to load: {doc.error}",
            )
            self.assertGreater(
                len(doc.sections),
                0,
                f"Registered help doc {entry.doc_id!r} has no sections",
            )

    def test_organisms_doc_has_biology_sections(self) -> None:
        doc = load_help_document_by_id("organisms")
        section_titles = [s.title for s in doc.sections]
        self.assertIn("What an Organism Is", section_titles)
        self.assertIn("What the Genome Controls", section_titles)

    def test_reading_creatures_doc_has_visual_sections(self) -> None:
        doc = load_help_document_by_id("reading_creatures")
        section_titles = [s.title for s in doc.sections]
        self.assertIn("The Meaning of Organism Appearance", section_titles)
        self.assertIn("How to Watch Evolution Happen", section_titles)

    def test_predator_prey_doc_has_ecology_sections(self) -> None:
        doc = load_help_document_by_id("predator_prey")
        section_titles = [s.title for s in doc.sections]
        self.assertIn("Predator-Prey Overview", section_titles)
        self.assertIn("Depth Bands and Cross-Band Misses", section_titles)

    def test_quick_start_has_controls(self) -> None:
        doc = load_help_document_by_id("quick_start")
        section_titles = [s.title for s in doc.sections]
        self.assertIn("Basic Controls", section_titles)

    def test_controls_settings_has_glossary(self) -> None:
        doc = load_help_document_by_id("controls_settings")
        section_titles = [s.title for s in doc.sections]
        self.assertIn("Glossary", section_titles)

    def test_default_doc_id_exists_in_registry(self) -> None:
        self.assertIn(DEFAULT_HELP_DOC_ID, HELP_DOC_BY_ID)

    def test_load_unknown_doc_id_returns_error_document(self) -> None:
        doc = load_help_document_by_id("nonexistent")
        self.assertFalse(doc.ok)
        self.assertIn("Unknown Document", doc.title)

    def test_help_is_not_one_giant_flat_document(self) -> None:
        for entry in HELP_DOCUMENTS:
            doc = load_help_document_by_id(entry.doc_id)
            self.assertLessEqual(
                len(doc.sections),
                15,
                f"Help doc {entry.doc_id!r} has {len(doc.sections)} sections — should be curated, not flat-dumped",
            )


class HelpNavigationTests(unittest.TestCase):
    def _document(self) -> HelpDocument:
        return HelpDocument(
            title="Guide",
            sections=(
                HelpSection("Start", 1, "Welcome"),
                HelpSection("Predators", 2, "Hunting and fleeing"),
                HelpSection("Food", 2, "Particles and cycles"),
            ),
            source_path=Path("guide.md"),
        )

    def test_selection_and_scroll_bounds_are_clamped(self) -> None:
        nav = HelpNavigation(self._document())

        nav.move_selection(10)
        self.assertEqual(nav.selected_section_index, 2)
        nav.move_selection(-10)
        self.assertEqual(nav.selected_section_index, 0)

        nav.set_content_bounds(line_count=20, visible_lines=5)
        nav.scroll_content(100)
        self.assertEqual(nav.content_scroll, 15)
        nav.scroll_content(-100)
        self.assertEqual(nav.content_scroll, 0)

    def test_search_query_filters_visible_sections_and_clear_restores_all(self) -> None:
        nav = HelpNavigation(self._document())

        nav.set_search_query("food")
        self.assertEqual(nav.visible_section_indices, [2])
        self.assertEqual(nav.selected_section_index, 2)

        nav.clear_search()
        self.assertEqual(nav.visible_section_indices, [0, 1, 2])


class HelpOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _overlay(self) -> HelpOverlay:
        document = HelpDocument(
            title="Guide",
            sections=(
                HelpSection("Overview", 1, "Welcome to Primordial."),
                HelpSection("Predator-Prey", 2, "Predators hunt prey. Food cycles matter."),
                HelpSection("Depth Bands", 2, "Surface, mid, and deep bands affect misses."),
            ),
            source_path=Path("guide.md"),
        )
        overlay = HelpOverlay(document)
        overlay.open(reload_document=False)
        return overlay

    def test_layout_has_positive_non_overlapping_regions(self) -> None:
        font = pygame.font.Font(None, 24)
        layout = calculate_help_layout(
            (1280, 720),
            section_titles=["Very Long Help Section Title That Should Fit"],
            title_font=font,
        )

        self.assertGreater(layout.nav_rect.width, 0)
        self.assertGreater(layout.content_rect.width, 0)
        self.assertLess(layout.nav_rect.right, layout.content_rect.x)
        self.assertLess(layout.content_rect.bottom, layout.footer_rect.y)

    def test_overlay_draws_headlessly_and_clicking_section_selects_it(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.fade = 20
        overlay.draw(screen)

        section_region = next(
            region
            for region in overlay._hit_regions
            if region.kind == "section" and region.section_index == 1
        )
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=section_region.rect.center)
        )

        self.assertEqual(overlay.navigation.selected_section_index, 1)

    def test_search_box_focus_typing_and_no_results_state(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.fade = 20
        overlay.draw(screen)

        search_region = next(region for region in overlay._hit_regions if region.kind == "search")
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=search_region.rect.center)
        )
        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, unicode="f"))
        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_o, unicode="o"))
        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_o, unicode="o"))

        self.assertTrue(overlay.navigation.search_focused)
        self.assertEqual(overlay.navigation.search_query, "foo")
        self.assertEqual(overlay.navigation.visible_section_indices, [1])

        overlay.navigation.set_search_query("zzzz")
        overlay.draw(screen)
        self.assertEqual(overlay.navigation.visible_section_indices, [])

    def test_escape_closes_without_mutating_selection(self) -> None:
        overlay = self._overlay()
        overlay.navigation.select_section(2)

        action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

        self.assertEqual(action, "close")
        self.assertEqual(overlay.fade_dir, -1)
        self.assertEqual(overlay.navigation.selected_section_index, 2)

    def test_tab_key_cycles_documents_when_multiple_documents(self) -> None:
        overlay = self._overlay()
        initial_doc_id = overlay.doc_id

        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))

        self.assertNotEqual(overlay.doc_id, initial_doc_id)

    def test_doc_tab_regions_present_when_multiple_documents(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.fade = 20
        overlay.draw(screen)

        doc_tab_regions = [r for r in overlay._hit_regions if r.kind == "doc_tab"]
        self.assertGreater(len(doc_tab_regions), 0)


class HelpNavigationScrollTests(unittest.TestCase):
    def test_nav_wheel_scroll_is_not_undone_by_ensure_selected_visible(self) -> None:
        sections = tuple(
            HelpSection(f"Section {i}", 2, f"Body {i}") for i in range(20)
        )
        document = HelpDocument(
            title="Guide",
            sections=sections,
            source_path=Path("guide.md"),
        )
        nav = HelpNavigation(document)
        visible_rows = 5
        nav.nav_first_visible = 0
        nav.scroll_nav(10, visible_rows)
        expected = nav.nav_first_visible
        nav.ensure_selected_nav_visible(visible_rows)
        self.assertEqual(nav.nav_first_visible, expected)

    def test_keyboard_selection_brings_selected_into_view(self) -> None:
        sections = tuple(
            HelpSection(f"Section {i}", 2, f"Body {i}") for i in range(20)
        )
        document = HelpDocument(
            title="Guide",
            sections=sections,
            source_path=Path("guide.md"),
        )
        nav = HelpNavigation(document)
        visible_rows = 5
        nav.nav_first_visible = 0
        for _ in range(15):
            nav.move_selection(1)
        nav.ensure_selected_nav_visible(visible_rows)
        self.assertGreaterEqual(nav.nav_first_visible, nav.selected_section_index - visible_rows + 1)


if __name__ == "__main__":
    unittest.main()
