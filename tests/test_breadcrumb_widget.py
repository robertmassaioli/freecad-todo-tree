# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Tests for BreadcrumbWidget truncation logic (requires PySide6 / Qt)."""

import pytest
from PySide6.QtCore import Qt

from freecad.TodoTree.breadcrumb_widget import BreadcrumbWidget


# ── fixture & helpers ──────────────────────────────────────────────────────────

CRUMB_W = 50   # fixed crumb width used by monkeypatched measurement helpers
SEP_W   = 10   # fixed separator width


@pytest.fixture()
def widget(qapp, monkeypatch):
    """BreadcrumbWidget with deterministic fixed-width font metrics."""
    w = BreadcrumbWidget()
    monkeypatch.setattr(w, "_crumb_px", lambda label: CRUMB_W)
    monkeypatch.setattr(w, "_sep_px",   lambda: SEP_W)
    # ellipsis_w inside _compute_visible also uses fontMetrics; patch the
    # horizontalAdvance call by replacing the whole method through a subclass
    # trick isn't needed — _compute_visible calls self._sep_px() and
    # self._crumb_px() (both patched) but calls fontMetrics().horizontalAdvance("…")
    # directly for the ellipsis width. Patch that too via a minimal mock.
    import types
    class _FakeFM:
        def horizontalAdvance(self, text):
            return CRUMB_W - 12   # simulate "…" text narrower than a full crumb
    w.fontMetrics = lambda: _FakeFM()
    w.resize(500, 30)
    return w


def ids(nodes):
    return [n[0] for n in nodes]


def _path(*labels):
    """Build a path from label strings; uses label as node_id for simplicity."""
    result = []
    for i, lbl in enumerate(labels):
        node_id = "root" if lbl == "Root" else f"node_{i}"
        result.append((node_id, lbl if lbl != "Root" else "__root__"))
    return result


# Width arithmetic (all values in px):
#   CRUMB_W=50, SEP_W=10, ellipsis_w = (50-12)+12 = 50
#   Each crumb slot = SEP_W + CRUMB_W = 60 (except first, which has no leading sep)
#   n-crumb path natural width = CRUMB_W + (n-1)*(SEP_W+CRUMB_W)
#                               = 50 + (n-1)*60
#   With ellipsis replacing k middle crumbs:
#     first + sep + ellipsis + sep + last = 50+10+50+10+50 = 170
#     + each shown middle: + 60 per crumb


# ── _compute_visible: algorithm unit tests ─────────────────────────────────────

def test_single_crumb(widget):
    widget.set_path(_path("Root"))
    visible, hidden = widget._compute_visible()
    assert ids(visible) == ["root"]
    assert hidden == []


def test_two_crumbs_always_fit(widget):
    widget.set_path(_path("Root", "A"))
    visible, hidden = widget._compute_visible()
    assert len(visible) == 2
    assert hidden == []


def test_all_middle_crumbs_fit(widget):
    # Natural width of 4 crumbs = 50 + 3*60 = 230 px. Widget is 500px → all fit.
    widget.set_path(_path("Root", "A", "B", "Leaf"))
    visible, hidden = widget._compute_visible()
    assert ids(visible) == ["root", "node_1", "node_2", "node_3"]
    assert hidden == []


def test_one_middle_crumb_hidden(widget):
    # 5-crumb natural width = 50 + 4*60 = 290. Too wide for 250px.
    # With ellipsis instead of B and C:
    #   Root > A > … > Leaf = 50+10+50+10+50+10+50 = 230 px → fits in 250.
    # With ellipsis instead of C only:
    #   Root > A > B > … > Leaf = 50+10+50+10+50+10+50+10+50 = 290 → doesn't fit.
    # So only A should be shown.
    widget.resize(250, 30)
    widget.set_path(_path("Root", "A", "B", "C", "Leaf"))
    visible, hidden = widget._compute_visible()
    # First and last always present; A fits, B and C are hidden.
    assert visible[0][0] == "root"
    assert visible[-1][0] == "node_4"
    assert len(hidden) >= 1


def test_all_middle_crumbs_hidden_when_very_narrow(widget):
    # Width=170: exactly fits Root > … > Leaf (50+10+50+10+50=170).
    # No middle crumb can be added because adding any one requires also fitting
    # an ellipsis for the rest (or no ellipsis if it's the only middle crumb).
    # One middle crumb with no ellipsis = 50+10+50+10+50=170. Let's use 2 middle
    # crumbs so both can't fit at 170px.
    widget.resize(170, 30)
    widget.set_path(_path("Root", "A", "B", "Leaf"))
    # Natural width of all: 50+10+50+10+50+10+50=230 > 170.
    # Adding A alone (no ellipsis for B):
    #   running(110) + needed(60) + ellipsis_slot(60) = 230 > 170 → A fails.
    # (running = first+sep+last = 50+10+50=110)
    visible, hidden = widget._compute_visible()
    assert visible[0][0] == "root"
    assert visible[-1][0] == "node_3"
    assert len(hidden) == 2


def test_last_middle_crumb_needs_no_ellipsis_slot(widget):
    # When there is exactly one middle crumb, no ellipsis slot is reserved for
    # remaining crumbs, so it can be included at a narrower width than if there
    # were two middle crumbs.
    #
    # 1 middle crumb: running(110) + needed_A(60) + ellipsis_slot(0) = 170.
    # 2 middle crumbs: running(110) + needed_A(60) + ellipsis_for_B(60) = 230.
    #
    # At width=200px (available=188): 1-crumb case fits (170≤188), 2-crumb case
    # does not include A because 230>188. This verifies the no-slot optimisation.
    widget.resize(200, 30)  # available = 200 - 12 = 188

    # One middle crumb fits.
    widget.set_path(_path("Root", "A", "Leaf"))
    visible, hidden = widget._compute_visible()
    assert len(visible) == 3
    assert hidden == []

    # Two middle crumbs: A cannot be included because the ellipsis slot for B
    # would push the total over 188px.
    widget.set_path(_path("Root", "A", "B", "Leaf"))
    visible2, hidden2 = widget._compute_visible()
    assert ids(visible2) == ["root", "node_3"]   # only Root and Leaf
    assert len(hidden2) == 2


def test_exact_fit_boundary(widget):
    # Natural width of 3-crumb path = 50 + 2*60 = 170. Widget at exactly 170px.
    widget.resize(170 + 12, 30)  # +12 for the 6px margins on each side
    widget.set_path(_path("Root", "A", "Leaf"))
    visible, hidden = widget._compute_visible()
    assert len(visible) == 3
    assert hidden == []


def test_greedy_includes_as_many_as_possible(widget):
    # 6-crumb path. Wide enough for Root + 2 middle + … + Leaf but not all 4 middle.
    # Natural: 50+5*60=350. Too wide for 290px.
    # Root > A > B > … > Leaf = 50+10+50+10+50+10+50+10+50 = 290 → fits in 290.
    # Check A fits: running(110)+needed(60)+ellipsis_for(B,C,D=3 left → 60) = 230 ≤ 290 ✓
    # Check B fits: running(170)+needed(60)+ellipsis_for(C,D=2 left → 60) = 290 ≤ 290 ✓
    # Check C fits: running(230)+needed(60)+ellipsis_for(D=1 left → 60) = 350 > 290 ✗
    widget.resize(290 + 12, 30)
    widget.set_path(_path("Root", "A", "B", "C", "D", "Leaf"))
    visible, hidden = widget._compute_visible()
    visible_ids = ids(visible)
    assert visible_ids[0]  == "root"
    assert visible_ids[-1] == "node_5"
    # A and B visible, C and D hidden.
    assert len(visible) == 4    # root, A, B, Leaf
    assert len(hidden) == 2     # C, D


# ── widget rendering ────────────────────────────────────────────────────────────

def test_set_path_empty(widget):
    widget.set_path([])
    # Should not crash and layout should just have a stretch.
    assert widget._layout.count() >= 0


def test_set_path_single_renders_bold_root(widget):
    widget.set_path(_path("Root"))
    widget._relayout()
    # Only one label widget (the bold current crumb) + 1 stretch item.
    # We can verify by counting non-stretch layout items.
    widgets = [widget._layout.itemAt(i).widget()
               for i in range(widget._layout.count())
               if widget._layout.itemAt(i).widget()]
    assert len(widgets) == 1


def test_nodeClicked_emitted_on_ancestor_button(qapp, monkeypatch):
    w = BreadcrumbWidget()
    monkeypatch.setattr(w, "_crumb_px", lambda label: CRUMB_W)
    monkeypatch.setattr(w, "_sep_px",   lambda: SEP_W)
    import types
    class _FakeFM:
        def horizontalAdvance(self, text): return CRUMB_W - 12
    w.fontMetrics = lambda: _FakeFM()
    w.resize(500, 30)

    path = [("root", "__root__"), ("a", "A"), ("b", "B")]
    w.set_path(path)

    emitted = []
    w.nodeClicked.connect(emitted.append)

    # Find the "Root" button (first non-stretch item).
    buttons = [w._layout.itemAt(i).widget()
               for i in range(w._layout.count())
               if isinstance(w._layout.itemAt(i).widget(), __import__(
                   'PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton)]
    root_btn = next(b for b in buttons if b.text() == "Root")
    root_btn.click()

    assert emitted == ["root"]


def test_display_converts_root_sentinel(widget):
    assert widget._display("__root__") == "Root"
    assert widget._display("My Task") == "My Task"
