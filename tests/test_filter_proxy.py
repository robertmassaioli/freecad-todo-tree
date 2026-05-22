# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Tests for DoneFilterProxy (requires PySide6 / Qt)."""

import pytest
from PySide6.QtCore import Qt, QModelIndex

from freecad.TodoTree.todo_model import TodoTree, EMPTY_TREE
from freecad.TodoTree.todo_item_model import TodoItemModel
from freecad.TodoTree.filter_proxy import DoneFilterProxy
from tests.conftest import make_fc_object


# ── fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def stack(qapp):
    """Return (source_model, proxy) with shape root → [A(done), B(undone) → [C(done)]]."""
    tree = TodoTree()
    a = tree.add_child("root", "A")
    tree.set_done(a.id, True)
    b = tree.add_child("root", "B")
    c = tree.add_child(b.id, "C")
    tree.set_done(c.id, True)

    fc = make_fc_object(tree.to_json())
    model = TodoItemModel(tree, fc)
    proxy = DoneFilterProxy()
    proxy.setSourceModel(model)
    return model, proxy, a, b, c


# ── show_done=True (default) ───────────────────────────────────────────────────

def test_show_done_true_shows_all_top_level_rows(stack):
    model, proxy, a, b, c = stack
    assert proxy.rowCount(QModelIndex()) == 2


def test_show_done_true_shows_nested_done_rows(stack):
    model, proxy, a, b, c = stack
    b_proxy_idx = proxy.mapFromSource(model.index_for_node(b.id))
    assert proxy.rowCount(b_proxy_idx) == 1


# ── show_done=False ────────────────────────────────────────────────────────────

def test_show_done_false_hides_done_top_level_items(stack):
    model, proxy, a, b, c = stack
    proxy.set_show_done(False)
    assert proxy.rowCount(QModelIndex()) == 1


def test_show_done_false_only_shows_undone_items(stack):
    model, proxy, a, b, c = stack
    proxy.set_show_done(False)
    idx = proxy.index(0, 0, QModelIndex())
    node_id = proxy.data(idx, Qt.UserRole)
    assert node_id == b.id


def test_show_done_false_hides_done_children(stack):
    model, proxy, a, b, c = stack
    proxy.set_show_done(False)
    b_proxy_idx = proxy.mapFromSource(model.index_for_node(b.id))
    assert proxy.rowCount(b_proxy_idx) == 0


# ── set_show_done idempotency ──────────────────────────────────────────────────

def test_set_show_done_same_value_is_noop(stack, monkeypatch):
    model, proxy, a, b, c = stack
    invalidate_calls = []
    monkeypatch.setattr(proxy, "invalidateFilter", lambda: invalidate_calls.append(1))
    proxy.set_show_done(True)  # already True
    assert invalidate_calls == []


def test_set_show_done_different_value_invalidates(stack, monkeypatch):
    model, proxy, a, b, c = stack
    invalidate_calls = []
    monkeypatch.setattr(proxy, "invalidateFilter", lambda: invalidate_calls.append(1))
    proxy.set_show_done(False)
    assert len(invalidate_calls) == 1


# ── show_done accessor ─────────────────────────────────────────────────────────

def test_show_done_accessor(stack):
    model, proxy, a, b, c = stack
    assert proxy.show_done() is True
    proxy.set_show_done(False)
    assert proxy.show_done() is False


# ── dropMimeData row translation ───────────────────────────────────────────────

def test_drop_mime_data_row_translation_with_filter_active(stack):
    """
    When show_done=False a done item is hidden, shifting visible row numbers.
    dropMimeData must translate the proxy row back to the correct source row
    before forwarding to the source model.
    """
    model, proxy, a, b, c = stack
    proxy.set_show_done(False)
    # Only B is visible at root level (A is done and hidden).
    # Drag B and drop it at proxy row=0 under root.
    b_proxy_idx = proxy.mapFromSource(model.index_for_node(b.id))
    mime = model.mimeData([model.index_for_node(b.id)])
    # Drop at row=0 under root (proxy coordinate; source row=0 maps here too
    # because we're dropping at the top without the filter shifting things).
    result = proxy.dropMimeData(mime, Qt.MoveAction, 0, 0, QModelIndex())
    assert result is True
