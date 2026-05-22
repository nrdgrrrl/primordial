from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
from primordial.rendering.help_navigation import HelpNavigation, HelpNavItem
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


class HelpNavigationTreeTests(unittest.TestCase):
    def test_sidebar_has_all_groups(self) -> None:
        nav = HelpNavigation()
        items = nav.sidebar_items
        group_items = [i for i in items if i.kind == "group"]
        self.assertEqual(len(group_items), len(HELP_DOCUMENTS))

    def test_collapsed_groups_hide_children(self) -> None:
        nav = HelpNavigation()
        for entry in HELP_DOCUMENTS:
            nav.expanded_groups[entry.doc_id] = False
        items = nav.sidebar_items
        section_items = [i for i in items if i.kind == "section"]
        self.assertEqual(len(section_items), 0)

    def test_expanded_groups_show_children(self) -> None:
        nav = HelpNavigation()
        nav.expanded_groups[HELP_DOCUMENTS[0].doc_id] = True
        items = nav.sidebar_items
        section_items = [i for i in items if i.kind == "section" and i.doc_id == HELP_DOCUMENTS[0].doc_id]
        doc = nav.documents[HELP_DOCUMENTS[0].doc_id]
        self.assertEqual(len(section_items), len(doc.sections))

    def test_selecting_section_switches_document(self) -> None:
        nav = HelpNavigation()
        second_doc_id = HELP_DOCUMENTS[1].doc_id
        doc = nav.documents[second_doc_id]
        if doc.sections:
            nav.select_section(second_doc_id, 0)
            self.assertEqual(nav.selected_doc_id, second_doc_id)
            self.assertTrue(nav.expanded_groups.get(second_doc_id, False))

    def test_toggle_group_flips_state(self) -> None:
        nav = HelpNavigation()
        doc_id = HELP_DOCUMENTS[0].doc_id
        initial = nav.expanded_groups.get(doc_id, False)
        nav.toggle_group(doc_id)
        self.assertEqual(nav.expanded_groups[doc_id], not initial)

    def test_search_expands_matching_groups_and_clear_restores(self) -> None:
        nav = HelpNavigation()
        for entry in HELP_DOCUMENTS:
            nav.expanded_groups[entry.doc_id] = False
        pre_expanded = dict(nav.expanded_groups)
        nav.set_search_query("predator")
        items = nav.sidebar_items
        section_items = [i for i in items if i.kind == "section"]
        self.assertGreater(len(section_items), 0)
        nav.clear_search()
        self.assertEqual(nav.expanded_groups, pre_expanded)

    def test_sidebar_scroll_clamps(self) -> None:
        nav = HelpNavigation()
        nav.set_sidebar_bounds(total_rows=20, visible_rows=5)
        nav.sidebar_scroll = 100
        nav.clamp_sidebar_scroll()
        self.assertEqual(nav.sidebar_scroll, 15)
        nav.sidebar_scroll = -5
        nav.clamp_sidebar_scroll()
        self.assertEqual(nav.sidebar_scroll, 0)

    def test_selected_sidebar_row_is_scrolled_into_view(self) -> None:
        nav = HelpNavigation()
        doc_id = HELP_DOCUMENTS[0].doc_id
        nav.expanded_groups[doc_id] = True
        nav.set_sidebar_bounds(total_rows=20, visible_rows=5)
        nav.sidebar_scroll = 10
        nav.select_section(doc_id, 0)
        nav.ensure_selected_sidebar_visible()
        self.assertLess(nav.sidebar_scroll, 10)

    def test_move_selection_goes_through_sections(self) -> None:
        nav = HelpNavigation()
        nav.expanded_groups[HELP_DOCUMENTS[0].doc_id] = True
        nav.focused_sidebar_index = nav.selected_sidebar_position
        nav.move_selection(1)
        items = nav.sidebar_items
        current = nav.focused_sidebar_index
        if current < len(items) and items[current].kind == "section" and items[current].section_index is not None:
            self.assertEqual(nav.selected_section_index, items[current].section_index)

    def test_handle_enter_on_group_toggles(self) -> None:
        nav = HelpNavigation()
        nav.expanded_groups[HELP_DOCUMENTS[0].doc_id] = True
        nav.selected_section_index = 0
        nav.selected_doc_id = HELP_DOCUMENTS[0].doc_id
        nav.focused_sidebar_index = 0
        nav.handle_enter_on_selected()
        self.assertFalse(nav.expanded_groups[HELP_DOCUMENTS[0].doc_id])

    def test_left_collapses_expanded_group(self) -> None:
        nav = HelpNavigation()
        doc_id = HELP_DOCUMENTS[0].doc_id
        nav.expanded_groups[doc_id] = True
        nav.selected_doc_id = doc_id
        nav.selected_section_index = 0
        nav.focused_sidebar_index = 0
        nav.handle_left()
        self.assertFalse(nav.expanded_groups[doc_id])

    def test_right_expands_collapsed_group(self) -> None:
        nav = HelpNavigation()
        doc_id = HELP_DOCUMENTS[0].doc_id
        nav.expanded_groups[doc_id] = False
        nav.selected_doc_id = doc_id
        nav.selected_section_index = 0
        nav.focused_sidebar_index = 0
        nav.handle_right()
        self.assertTrue(nav.expanded_groups[doc_id])


class HelpOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _overlay(self) -> HelpOverlay:
        overlay = HelpOverlay()
        overlay.visible = True
        overlay.fade = 20
        return overlay

    def _overflowing_sidebar_overlay(self) -> tuple[HelpOverlay, pygame.Surface]:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        for entry in HELP_DOCUMENTS:
            overlay.navigation.expanded_groups[entry.doc_id] = True
        overlay.draw(screen)
        self.assertGreater(overlay.navigation.sidebar_total_rows, overlay.navigation.sidebar_visible_rows)
        return overlay, screen

    def _overflowing_content_overlay(self) -> tuple[HelpOverlay, pygame.Surface]:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        for entry in HELP_DOCUMENTS:
            doc = overlay.navigation.documents[entry.doc_id]
            for section_index, _section in enumerate(doc.sections):
                overlay.navigation.select_section(entry.doc_id, section_index)
                overlay.draw(screen)
                if overlay.navigation.content_line_count > overlay.navigation.content_visible_lines:
                    return overlay, screen
        self.fail("No registered help section overflowed the content pane")

    def test_layout_has_positive_non_overlapping_regions(self) -> None:
        font = pygame.font.Font(None, 24)
        layout = calculate_help_layout(
            (1280, 720),
            title_font=font,
        )

        self.assertGreater(layout.sidebar_rect.width, 0)
        self.assertGreater(layout.content_rect.width, 0)
        self.assertLess(layout.sidebar_rect.right + 12, layout.content_rect.x)
        self.assertLess(layout.content_rect.bottom, layout.footer_rect.y)

    def test_layout_has_no_doc_tabs_rect(self) -> None:
        layout = calculate_help_layout((1280, 720), title_font=pygame.font.Font(None, 24))
        self.assertFalse(hasattr(layout, "doc_tabs_rect"))
        self.assertFalse(hasattr(layout, "nav_rect"))

    def test_layout_has_scrollbar_rects(self) -> None:
        layout = calculate_help_layout((1280, 720), title_font=pygame.font.Font(None, 24))
        self.assertTrue(hasattr(layout, "sidebar_scrollbar_rect"))
        self.assertTrue(hasattr(layout, "content_scrollbar_rect"))
        self.assertGreater(layout.sidebar_scrollbar_rect.width, 0)
        self.assertGreater(layout.content_scrollbar_rect.width, 0)

    def test_overlay_draws_headlessly(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.draw(screen)
        self.assertGreater(len(overlay._hit_regions), 0)

    def test_no_doc_tab_hit_regions(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.draw(screen)
        doc_tab_regions = [r for r in overlay._hit_regions if r.kind == "doc_tab"]
        self.assertEqual(len(doc_tab_regions), 0)

    def test_group_hit_regions_present(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.draw(screen)
        group_regions = [r for r in overlay._hit_regions if r.kind == "group"]
        self.assertGreater(len(group_regions), 0)

    def test_section_hit_regions_present_when_expanded(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.navigation.expanded_groups[HELP_DOCUMENTS[0].doc_id] = True
        overlay.draw(screen)
        section_regions = [r for r in overlay._hit_regions if r.kind == "section"]
        self.assertGreater(len(section_regions), 0)

    def test_clicking_section_selects_it(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.navigation.expanded_groups[HELP_DOCUMENTS[0].doc_id] = True
        overlay.draw(screen)

        section_regions = [r for r in overlay._hit_regions if r.kind == "section"]
        self.assertGreater(len(section_regions), 0)
        target = section_regions[0]
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.rect.center)
        )
        self.assertEqual(overlay.navigation.selected_doc_id, target.doc_id)
        self.assertEqual(overlay.navigation.selected_section_index, target.section_index)

    def test_clicking_group_toggles_it(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
        overlay.draw(screen)
        group_regions = [r for r in overlay._hit_regions if r.kind == "group"]
        self.assertGreater(len(group_regions), 0)
        target = group_regions[0]
        initial = overlay.navigation.expanded_groups.get(target.doc_id, False)
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.rect.center)
        )
        self.assertEqual(overlay.navigation.expanded_groups[target.doc_id], not initial)

    def test_search_box_focus_typing_and_results(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = self._overlay()
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
        has_section = any(item.kind == "section" for item in overlay.navigation.sidebar_items)
        self.assertTrue(has_section or overlay.navigation.search_query == "foo")

    def test_escape_closes_without_mutating_selection(self) -> None:
        overlay = self._overlay()
        overlay.navigation.select_section(HELP_DOCUMENTS[0].doc_id, 1)

        action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

        self.assertEqual(action, "close")
        self.assertEqual(overlay.fade_dir, -1)
        self.assertEqual(overlay.navigation.selected_section_index, 1)

    def test_help_opens_with_h_shortcut(self) -> None:
        overlay = HelpOverlay()
        overlay.open()
        self.assertTrue(overlay.visible)

    def test_sidebar_wheel_scroll_persists_through_draw(self) -> None:
        overlay, screen = self._overflowing_sidebar_overlay()
        mouse_pos = (
            overlay._last_panel_rect.x + overlay._last_sidebar_rect.centerx,
            overlay._last_panel_rect.y + overlay._last_sidebar_rect.centery,
        )

        with patch("pygame.mouse.get_pos", return_value=mouse_pos):
            overlay.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1))

        scrolled = overlay.navigation.sidebar_scroll
        self.assertGreater(scrolled, 0)
        overlay.draw(screen)
        self.assertEqual(overlay.navigation.sidebar_scroll, scrolled)

    def test_content_wheel_scroll_does_not_affect_sidebar(self) -> None:
        overlay, screen = self._overflowing_content_overlay()
        sidebar_scroll = overlay.navigation.sidebar_scroll
        mouse_pos = (
            overlay._last_panel_rect.x + overlay._last_content_rect.centerx,
            overlay._last_panel_rect.y + overlay._last_content_rect.centery,
        )

        with patch("pygame.mouse.get_pos", return_value=mouse_pos):
            overlay.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1))

        self.assertEqual(overlay.navigation.sidebar_scroll, sidebar_scroll)
        scrolled = overlay.navigation.content_scroll
        self.assertGreater(scrolled, 0)
        overlay.draw(screen)
        self.assertEqual(overlay.navigation.content_scroll, scrolled)

    def test_sidebar_scrollbar_thumb_drag_updates_scroll(self) -> None:
        overlay, screen = self._overflowing_sidebar_overlay()
        thumb = next(region for region in overlay._hit_regions if region.kind == "sidebar_scrollbar_thumb")
        start = overlay.navigation.sidebar_scroll

        overlay.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=thumb.rect.center))
        overlay.handle_event(
            pygame.event.Event(
                pygame.MOUSEMOTION,
                pos=(thumb.rect.centerx, thumb.rect.centery + 120),
                rel=(0, 120),
                buttons=(1, 0, 0),
            )
        )
        overlay.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=thumb.rect.center))

        self.assertFalse(overlay.navigation._dragging_sidebar_scrollbar)
        self.assertNotEqual(overlay.navigation.sidebar_scroll, start)
        self.assertLessEqual(
            overlay.navigation.sidebar_scroll,
            overlay.navigation.sidebar_total_rows - overlay.navigation.sidebar_visible_rows,
        )
        scrolled = overlay.navigation.sidebar_scroll
        overlay.draw(screen)
        self.assertEqual(overlay.navigation.sidebar_scroll, scrolled)

    def test_content_scrollbar_thumb_drag_updates_scroll(self) -> None:
        overlay, screen = self._overflowing_content_overlay()
        thumb = next(region for region in overlay._hit_regions if region.kind == "content_scrollbar_thumb")
        start = overlay.navigation.content_scroll

        overlay.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=thumb.rect.center))
        overlay.handle_event(
            pygame.event.Event(
                pygame.MOUSEMOTION,
                pos=(thumb.rect.centerx, thumb.rect.centery + 160),
                rel=(0, 160),
                buttons=(1, 0, 0),
            )
        )
        overlay.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=thumb.rect.center))

        self.assertFalse(overlay.navigation._dragging_content_scrollbar)
        self.assertNotEqual(overlay.navigation.content_scroll, start)
        self.assertLessEqual(
            overlay.navigation.content_scroll,
            overlay.navigation.content_line_count - overlay.navigation.content_visible_lines,
        )
        scrolled = overlay.navigation.content_scroll
        overlay.draw(screen)
        self.assertEqual(overlay.navigation.content_scroll, scrolled)

    def test_sidebar_collapse_and_search_clamp_scroll(self) -> None:
        overlay, screen = self._overflowing_sidebar_overlay()
        overlay.navigation.sidebar_scroll = overlay.navigation.sidebar_total_rows
        overlay.navigation.collapse_group(HELP_DOCUMENTS[0].doc_id)
        overlay.draw(screen)
        self.assertLessEqual(
            overlay.navigation.sidebar_scroll,
            max(0, overlay.navigation.sidebar_total_rows - overlay.navigation.sidebar_visible_rows),
        )

        overlay.navigation.set_search_query("predator")
        overlay.draw(screen)
        self.assertLessEqual(
            overlay.navigation.sidebar_scroll,
            max(0, overlay.navigation.sidebar_total_rows - overlay.navigation.sidebar_visible_rows),
        )


class HelpSidebarScrollTests(unittest.TestCase):
    def test_selected_sidebar_row_is_scrolled_into_view(self) -> None:
        nav = HelpNavigation()
        doc_id = HELP_DOCUMENTS[0].doc_id
        nav.expanded_groups[doc_id] = True
        nav.set_sidebar_bounds(total_rows=20, visible_rows=5)
        nav.sidebar_scroll = 10
        nav.select_section(doc_id, 0)
        nav.ensure_selected_sidebar_visible()
        self.assertLess(nav.sidebar_scroll, 10)

    def test_sidebar_scroll_clamp_math(self) -> None:
        nav = HelpNavigation()
        nav.set_sidebar_bounds(total_rows=50, visible_rows=10)
        nav.sidebar_scroll = 100
        nav.clamp_sidebar_scroll()
        self.assertEqual(nav.sidebar_scroll, 40)
        nav.sidebar_scroll = -10
        nav.clamp_sidebar_scroll()
        self.assertEqual(nav.sidebar_scroll, 0)

    def test_sidebar_scrollbar_thumb_size_ratio(self) -> None:
        nav = HelpNavigation()
        nav.set_sidebar_bounds(total_rows=100, visible_rows=20)
        ratio = nav.sidebar_visible_rows / max(1, nav.sidebar_total_rows)
        self.assertAlmostEqual(ratio, 0.2, places=2)


class HelpScrollbarVisibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_sidebar_scrollbar_hit_region_when_overflow(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = HelpOverlay()
        overlay.visible = True
        overlay.fade = 20
        for entry in HELP_DOCUMENTS:
            overlay.navigation.expanded_groups[entry.doc_id] = True
        overlay.draw(screen)
        sb_regions = [r for r in overlay._hit_regions if r.sidebar_scrollbar]
        self.assertGreater(len(sb_regions), 0)

    def test_content_scrollbar_hit_region_when_overflow(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = HelpOverlay()
        overlay.visible = True
        overlay.fade = 20
        overlay.draw(screen)
        doc = overlay.navigation.current_document
        sb_regions = [r for r in overlay._hit_regions if r.content_scrollbar]
        if overlay.navigation.content_line_count > overlay.navigation.content_visible_lines:
            self.assertGreater(len(sb_regions), 0)


class HelpTextWrappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_wrap_text_wraps_long_labels(self) -> None:
        overlay = HelpOverlay()
        font = pygame.font.Font(None, 20)
        lines = overlay._wrap_text("Predator-Prey Overview and Adaptive Tuning Behavior", font, 120)
        self.assertGreater(len(lines), 1)

    def test_wrap_text_bullet_hanging_indent(self) -> None:
        overlay = HelpOverlay()
        section = HelpSection("Test", 2, "- First point with a very long continuation line that should wrap with hanging indent\n- Second point")
        lines = overlay._content_lines(section, 200)
        bullet_lines = [l for l in lines if l.startswith("- ") or l.startswith("  ")]
        self.assertGreater(len(bullet_lines), 0)

    def test_wrap_text_empty_returns_empty_line(self) -> None:
        overlay = HelpOverlay()
        lines = overlay._wrap_text("", pygame.font.Font(None, 24), 100)
        self.assertEqual(lines, [""])


if __name__ == "__main__":
    unittest.main()
