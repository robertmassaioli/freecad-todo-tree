# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Tests for TodoItemModel (requires PySide6 / Qt)."""

import json
import pytest
from unittest.mock import MagicMock, patch, call

from PySide6.QtCore import Qt, QModelIndex, QMimeData

from freecad.TodoTree.todo_model import TodoTree, EMPTY_TREE
from freecad.TodoTree.todo_item_model import TodoItemModel
from tests.conftest import make_fc_object


# ── fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def model(qapp):
    tree = TodoTree.from_dict(EMPTY_TREE)
    fc = make_fc_object()
    m = TodoItemModel(tree, fc)
    return m


@pytest.fixture()
def populated_model(qapp):
    """Model with shape: root → [A, B → [C, D]]."""
    tree = TodoTree()
    a = tree.add_child("root", "A")
    b = tree.add_child("root", "B")
    c = tree.add_child(b.id, "C")
    d = tree.add_child(b.id, "D")
    fc = make_fc_object(tree.to_json())
    m = TodoItemModel(tree, fc)
    return m, a, b, c, d


# ── rowCount / columnCount ──────────────────────────────────────────────────────

def test_row_count_empty(model):
    assert model.rowCount(QModelIndex()) == 0


def test_column_count(model):
    assert model.columnCount(QModelIndex()) == 1


def test_row_count_after_add(model):
    model.add_child(QModelIndex(), "Task")
    assert model.rowCount(QModelIndex()) == 1


def test_row_count_nested(populated_model):
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    assert m.rowCount(b_idx) == 2


# ── data() ─────────────────────────────────────────────────────────────────────

def test_data_display_role(model):
    model.add_child(QModelIndex(), "Hello")
    idx = model.index(0, 0, QModelIndex())
    assert model.data(idx, Qt.DisplayRole) == "Hello"


def test_data_edit_role(model):
    model.add_child(QModelIndex(), "Hello")
    idx = model.index(0, 0, QModelIndex())
    assert model.data(idx, Qt.EditRole) == "Hello"


def test_data_check_state_undone(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    assert model.data(idx, Qt.CheckStateRole) == 0


def test_data_check_state_done(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    model.setData(idx, 2, Qt.CheckStateRole)
    assert model.data(idx, Qt.CheckStateRole) == 2


def test_data_user_role_returns_node_id(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    node_id = model.data(idx, Qt.UserRole)
    assert isinstance(node_id, str)
    assert model._tree.get_node(node_id) is not None


def test_data_invalid_index_returns_none(model):
    assert model.data(QModelIndex(), Qt.DisplayRole) is None


# ── flags() ────────────────────────────────────────────────────────────────────

def test_flags_on_valid_index(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    flags = model.flags(idx)
    assert flags & Qt.ItemIsEnabled
    assert flags & Qt.ItemIsSelectable
    assert flags & Qt.ItemIsEditable
    assert flags & Qt.ItemIsUserCheckable
    assert flags & Qt.ItemIsDragEnabled
    assert flags & Qt.ItemIsDropEnabled


def test_flags_on_invalid_index_allows_drop(model):
    flags = model.flags(QModelIndex())
    assert flags & Qt.ItemIsDropEnabled


# ── setData() ──────────────────────────────────────────────────────────────────

def test_set_data_edit_role_renames(model):
    model.add_child(QModelIndex(), "Old")
    idx = model.index(0, 0, QModelIndex())
    result = model.setData(idx, "New", Qt.EditRole)
    assert result is True
    assert model.data(idx, Qt.DisplayRole) == "New"


def test_set_data_empty_text_rejected(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    result = model.setData(idx, "   ", Qt.EditRole)
    assert result is False
    assert model.data(idx, Qt.DisplayRole) == "Task"


def test_set_data_same_text_rejected(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    result = model.setData(idx, "Task", Qt.EditRole)
    assert result is False


def test_set_data_check_state_marks_done(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    result = model.setData(idx, 2, Qt.CheckStateRole)
    assert result is True
    assert model.data(idx, Qt.CheckStateRole) == 2


def test_set_data_check_state_marks_undone(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    model.setData(idx, 2, Qt.CheckStateRole)
    result = model.setData(idx, 0, Qt.CheckStateRole)
    assert result is True
    assert model.data(idx, Qt.CheckStateRole) == 0


def test_set_data_check_state_same_value_rejected(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    result = model.setData(idx, 0, Qt.CheckStateRole)
    assert result is False


def test_set_data_opens_and_commits_transaction(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    model.setData(idx, "Renamed", Qt.EditRole)
    model._fc_object.Document.openTransaction.assert_called()
    model._fc_object.Document.commitTransaction.assert_called()


# ── add_child / remove_node ────────────────────────────────────────────────────

def test_add_child_returns_valid_index(model):
    idx = model.add_child(QModelIndex(), "Task")
    assert idx.isValid()


def test_add_child_under_parent(populated_model):
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    new_idx = m.add_child(b_idx, "E")
    assert new_idx.isValid()
    assert m.rowCount(b_idx) == 3


def test_remove_node_decreases_row_count(model):
    model.add_child(QModelIndex(), "Task")
    idx = model.index(0, 0, QModelIndex())
    model.remove_node(idx)
    assert model.rowCount(QModelIndex()) == 0


def test_remove_node_removes_subtree(populated_model):
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    m.remove_node(b_idx)
    assert m.rowCount(QModelIndex()) == 1
    assert m._tree.get_node(c.id) is None
    assert m._tree.get_node(d.id) is None


# ── outdent_node / indent_node ─────────────────────────────────────────────────

def test_outdent_node_raises_level(populated_model):
    m, a, b, c, d = populated_model
    c_idx = m.index_for_node(c.id)
    m.outdent_node(c_idx)
    assert m._tree.get_node(c.id)._parent is m._tree.root


def test_indent_node_lowers_level(populated_model):
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    m.indent_node(b_idx)
    assert m._tree.get_node(b.id)._parent is m._tree.get_node(a.id)


# ── index_for_node ─────────────────────────────────────────────────────────────

def test_index_for_node_valid(populated_model):
    m, a, b, c, d = populated_model
    idx = m.index_for_node(c.id)
    assert idx.isValid()
    assert m.data(idx, Qt.DisplayRole) == "C"


def test_index_for_node_root_returns_invalid(model):
    assert not model.index_for_node("root").isValid()


def test_index_for_node_unknown_returns_invalid(model):
    assert not model.index_for_node("ghost").isValid()


# ── dropMimeData: same-parent downward-move regression ─────────────────────────

def test_drop_same_parent_downward_uses_correct_bm_dest(populated_model):
    """
    Regression: when moving a node downward in the same parent the destination
    row passed to beginMoveRows must be insert_row (pre-removal coordinate) but
    effective_insert_row to move_node must be insert_row - 1 (post-removal).

    If the code erroneously passes insert_row - 1 to both, Qt emits
    "invalid sourceRow" warnings and the move silently no-ops.
    """
    m, a, b, c, d = populated_model
    # Move C (row 0 in B) to after D (insert_row=2 in B).
    b_idx = m.index_for_node(b.id)
    mime = m.mimeData([m.index_for_node(c.id)])
    # Drop at row=2 under B — that's position after D
    result = m.dropMimeData(mime, Qt.MoveAction, 2, 0, b_idx)
    assert result is True
    b_node = m._tree.get_node(b.id)
    assert b_node.children[0].id == d.id
    assert b_node.children[1].id == c.id


def test_drop_same_parent_no_op_position_returns_true(populated_model):
    """Dropping a node one step below itself is a visual no-op; must return True."""
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    mime = m.mimeData([m.index_for_node(c.id)])
    # insert_row=1 with src_row=0 is the forbidden same-position drop
    result = m.dropMimeData(mime, Qt.MoveAction, 1, 0, b_idx)
    assert result is True
    # Order unchanged
    b_node = m._tree.get_node(b.id)
    assert b_node.children[0].id == c.id
    assert b_node.children[1].id == d.id


def test_drop_into_subtree_rejected(populated_model):
    """Cannot drag a parent into one of its own descendants."""
    m, a, b, c, d = populated_model
    b_idx = m.index_for_node(b.id)
    mime = m.mimeData([b_idx])
    c_idx = m.index_for_node(c.id)
    result = m.dropMimeData(mime, Qt.MoveAction, -1, 0, c_idx)
    assert result is False
