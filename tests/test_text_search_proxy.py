# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Tests for TextSearchProxy (requires PySide6 / Qt)."""

import json
import pytest
from unittest.mock import MagicMock
from PySide6.QtCore import Qt, QModelIndex

from freecad.TodoTree.todo_model import TodoTree, EMPTY_TREE
from freecad.TodoTree.todo_item_model import TodoItemModel
from freecad.TodoTree.filter_proxy import DoneFilterProxy, TextSearchProxy
from tests.conftest import make_fc_object


# ── fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def stack(qapp):
    """
    Full proxy chain: TodoItemModel → DoneFilterProxy → TextSearchProxy.
    Tree shape: root → [Alpha, Beta → [Gamma, Delta(done)], Epsilon]
    """
    tree = TodoTree()
    alpha   = tree.add_child("root", "Alpha")
    beta    = tree.add_child("root", "Beta")
    gamma   = tree.add_child(beta.id, "Gamma")
    delta   = tree.add_child(beta.id, "Delta")
    tree.set_done(delta.id, True)
    epsilon = tree.add_child("root", "Epsilon")

    fc = make_fc_object(tree.to_json())
    model   = TodoItemModel(tree, fc)
    done_p  = DoneFilterProxy()
    done_p.setSourceModel(model)
    search_p = TextSearchProxy()
    search_p.setSourceModel(done_p)

    return model, done_p, search_p, alpha, beta, gamma, delta, epsilon


# ── TextSearchProxy: empty text is a no-op ─────────────────────────────────────

def test_empty_search_passes_all_rows(stack):
    model, done_p, search_p, *_ = stack
    assert search_p.rowCount(QModelIndex()) == 3  # Alpha, Beta, Epsilon


def test_empty_search_after_text_restores_all_rows(stack):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("alpha")
    search_p.set_search_text("")
    assert search_p.rowCount(QModelIndex()) == 3


# ── TextSearchProxy: matching rows ─────────────────────────────────────────────

def test_exact_match_shown(stack):
    model, done_p, search_p, alpha, *_ = stack
    search_p.set_search_text("Alpha")
    assert search_p.rowCount(QModelIndex()) == 1
    idx = search_p.index(0, 0, QModelIndex())
    assert search_p.data(idx, Qt.DisplayRole) == "Alpha"


def test_substring_match(stack):
    model, done_p, search_p, alpha, beta, *_ = stack
    search_p.set_search_text("lph")   # matches Alpha
    assert search_p.rowCount(QModelIndex()) == 1


def test_case_insensitive_match(stack):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("ALPHA")
    assert search_p.rowCount(QModelIndex()) == 1


# ── TextSearchProxy: ancestor rows are kept for navigation ─────────────────────

def test_ancestor_shown_when_descendant_matches(stack):
    model, done_p, search_p, alpha, beta, gamma, *_ = stack
    search_p.set_search_text("gamma")  # Gamma is a child of Beta
    # Beta must be visible (so the user can navigate to Gamma)
    assert search_p.rowCount(QModelIndex()) == 1
    parent_idx = search_p.index(0, 0, QModelIndex())
    assert search_p.data(parent_idx, Qt.DisplayRole) == "Beta"
    # Gamma is visible under Beta
    assert search_p.rowCount(parent_idx) == 1
    child_idx = search_p.index(0, 0, parent_idx)
    assert search_p.data(child_idx, Qt.DisplayRole) == "Gamma"


def test_no_match_row_hidden(stack):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("zzz")
    assert search_p.rowCount(QModelIndex()) == 0


# ── interaction with DoneFilterProxy ───────────────────────────────────────────

def test_done_item_hidden_even_when_it_matches(stack):
    model, done_p, search_p, alpha, beta, gamma, delta, epsilon = stack
    done_p.set_show_done(False)
    search_p.set_search_text("delta")  # Delta is done and show_done=False
    # Delta is filtered by DoneFilterProxy before TextSearchProxy sees it,
    # so it should not appear in results.
    assert search_p.rowCount(QModelIndex()) == 0


def test_done_item_visible_when_show_done_true_and_matches(stack):
    model, done_p, search_p, alpha, beta, gamma, delta, epsilon = stack
    done_p.set_show_done(True)
    search_p.set_search_text("delta")
    # Beta is ancestor of Delta → Beta visible, Delta visible under it
    assert search_p.rowCount(QModelIndex()) == 1
    beta_idx = search_p.index(0, 0, QModelIndex())
    assert search_p.data(beta_idx, Qt.DisplayRole) == "Beta"
    # Two children visible under Beta when show_done=True: Gamma and Delta
    # But only Delta matches "delta", and Gamma doesn't — however Beta is already
    # shown (it's the ancestor), and Gamma is also shown because Beta was included.
    # Actually: filterAcceptsRow for Gamma → "gamma" doesn't contain "delta" →
    # check descendants of Gamma (none) → False. So Gamma is hidden.
    assert search_p.rowCount(beta_idx) == 1
    delta_idx = search_p.index(0, 0, beta_idx)
    assert search_p.data(delta_idx, Qt.DisplayRole) == "Delta"


def test_undone_descendant_match_shows_parent_when_show_done_false(stack):
    model, done_p, search_p, alpha, beta, gamma, delta, epsilon = stack
    done_p.set_show_done(False)
    search_p.set_search_text("gamma")
    # Gamma is undone → passes DoneFilterProxy → matched by text → Beta shown
    assert search_p.rowCount(QModelIndex()) == 1
    beta_idx = search_p.index(0, 0, QModelIndex())
    assert search_p.data(beta_idx, Qt.DisplayRole) == "Beta"


# ── set_search_text idempotency ────────────────────────────────────────────────

def test_set_same_text_does_not_invalidate(stack, monkeypatch):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("alpha")
    calls = []
    monkeypatch.setattr(search_p, "invalidateFilter", lambda: calls.append(1))
    search_p.set_search_text("alpha")   # same normalised value
    assert calls == []


def test_set_different_text_invalidates(stack, monkeypatch):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("alpha")
    calls = []
    monkeypatch.setattr(search_p, "invalidateFilter", lambda: calls.append(1))
    search_p.set_search_text("beta")
    assert len(calls) == 1


def test_whitespace_only_is_empty(stack):
    model, done_p, search_p, *_ = stack
    search_p.set_search_text("   ")
    assert search_p.search_text == ""
    assert search_p.rowCount(QModelIndex()) == 3


# ── dropMimeData through the full chain ────────────────────────────────────────

def test_drop_mime_data_through_full_chain(stack):
    """Drag-and-drop works correctly through both proxies with no filter active."""
    model, done_p, search_p, alpha, beta, gamma, delta, epsilon = stack
    # Move Epsilon (row 2 at root) to row 0 — an upward same-parent move.
    # Expected result after drop: [Epsilon, Alpha, Beta].
    mime = model.mimeData([model.index_for_node(epsilon.id)])
    result = search_p.dropMimeData(mime, Qt.MoveAction, 0, 0, QModelIndex())
    assert result is True
    assert model._tree.root.children[0].id == epsilon.id
