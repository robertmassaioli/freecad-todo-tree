# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Unit tests for TodoNode and TodoTree (pure Python, no Qt or FreeCAD needed)."""

import json
import pytest

from freecad.TodoTree.todo_model import TodoNode, TodoTree, EMPTY_TREE


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_tree():
    """Return a TodoTree with a known shape: root → [A, B → [C, D]]."""
    tree = TodoTree()
    a = tree.add_child("root", "A")
    b = tree.add_child("root", "B")
    c = tree.add_child(b.id, "C")
    d = tree.add_child(b.id, "D")
    return tree, a, b, c, d


# ── TodoNode ───────────────────────────────────────────────────────────────────

def test_todo_node_defaults():
    n = TodoNode("x", "hello")
    assert n.id == "x"
    assert n.text == "hello"
    assert n.done is False
    assert n.expanded is False
    assert n.children == []
    assert n._parent is None


# ── TodoTree: basics ───────────────────────────────────────────────────────────

def test_fresh_tree_has_root():
    tree = TodoTree()
    assert tree.root.id == "root"
    assert tree.get_node("root") is tree.root


def test_add_child_appears_in_parent():
    tree = TodoTree()
    node = tree.add_child("root", "Task")
    assert node in tree.root.children
    assert node._parent is tree.root


def test_add_child_registered_in_id_map():
    tree = TodoTree()
    node = tree.add_child("root", "Task")
    assert tree.get_node(node.id) is node


def test_get_node_unknown_returns_none():
    tree = TodoTree()
    assert tree.get_node("nonexistent") is None


def test_add_nested_child():
    tree, a, b, c, d = _build_tree()
    assert c._parent is b
    assert d._parent is b
    assert c in b.children
    assert d in b.children


# ── set_* mutations ────────────────────────────────────────────────────────────

def test_set_text():
    tree = TodoTree()
    n = tree.add_child("root", "Old")
    tree.set_text(n.id, "New")
    assert n.text == "New"


def test_set_done():
    tree = TodoTree()
    n = tree.add_child("root", "Task")
    assert n.done is False
    tree.set_done(n.id, True)
    assert n.done is True
    tree.set_done(n.id, False)
    assert n.done is False


def test_set_expanded():
    tree = TodoTree()
    n = tree.add_child("root", "Task")
    tree.set_expanded(n.id, True)
    assert n.expanded is True
    tree.set_expanded(n.id, False)
    assert n.expanded is False


def test_set_expanded_unknown_id_no_crash():
    tree = TodoTree()
    tree.set_expanded("ghost", True)  # should not raise


# ── remove_node ────────────────────────────────────────────────────────────────

def test_remove_node_removes_from_parent():
    tree, a, b, c, d = _build_tree()
    tree.remove_node(a.id)
    assert a not in tree.root.children


def test_remove_node_purges_id_map():
    tree, a, b, c, d = _build_tree()
    tree.remove_node(b.id)
    assert tree.get_node(b.id) is None
    assert tree.get_node(c.id) is None
    assert tree.get_node(d.id) is None


def test_remove_root_is_noop():
    tree = TodoTree()
    tree.remove_node("root")
    assert tree.get_node("root") is tree.root


# ── outdent_node ───────────────────────────────────────────────────────────────

def test_outdent_moves_node_up_one_level():
    tree, a, b, c, d = _build_tree()
    tree.outdent_node(c.id)
    # C should now be a direct child of root, placed after B
    assert c in tree.root.children
    assert c._parent is tree.root
    idx_b = tree.root.children.index(b)
    idx_c = tree.root.children.index(c)
    assert idx_c == idx_b + 1


def test_outdent_node_at_root_level_returns_false():
    tree, a, b, c, d = _build_tree()
    result = tree.outdent_node(a.id)
    assert result is False
    assert a in tree.root.children


def test_outdent_leaves_children_intact():
    """A node with children takes them along when outdented."""
    tree = TodoTree()
    parent = tree.add_child("root", "Parent")
    child = tree.add_child(parent.id, "Child")
    grandchild = tree.add_child(child.id, "Grandchild")

    tree.outdent_node(child.id)
    assert child in tree.root.children
    assert grandchild in child.children


# ── indent_node ────────────────────────────────────────────────────────────────

def test_indent_moves_node_under_previous_sibling():
    tree, a, b, c, d = _build_tree()
    # Indent A: A has no previous sibling, should fail.
    # Indent B: B's previous sibling is A, so B goes under A.
    result = tree.indent_node(b.id)
    assert result is True
    assert b in a.children
    assert b._parent is a
    assert b not in tree.root.children


def test_indent_first_child_returns_false():
    tree, a, b, c, d = _build_tree()
    result = tree.indent_node(a.id)
    assert result is False
    assert a in tree.root.children


def test_indent_roundtrip_with_outdent():
    """indent then outdent returns the node to its original position."""
    tree, a, b, c, d = _build_tree()
    original_siblings = list(tree.root.children)
    tree.indent_node(b.id)   # B goes under A
    tree.outdent_node(b.id)  # B comes back to root level, after A
    assert list(tree.root.children) == original_siblings


# ── move_node ──────────────────────────────────────────────────────────────────

def test_move_node_to_different_parent():
    tree, a, b, c, d = _build_tree()
    tree.move_node(a.id, b.id, 0)
    assert a in b.children
    assert a._parent is b
    assert a not in tree.root.children


def test_move_node_same_parent_upward():
    tree, a, b, c, d = _build_tree()
    # Move D before C (index 0 within B)
    tree.move_node(d.id, b.id, 0)
    assert b.children.index(d) == 0
    assert b.children.index(c) == 1


def test_move_node_same_parent_downward():
    tree, a, b, c, d = _build_tree()
    # Move C after D (insert_row 2 = end). After removing C, D is at 0, so C appends.
    tree.move_node(c.id, b.id, 2)
    assert b.children.index(d) == 0
    assert b.children.index(c) == 1


def test_move_node_to_end_of_list():
    tree, a, b, c, d = _build_tree()
    # Insert_row beyond the end is clamped to len(children).
    result = tree.move_node(a.id, b.id, 999)
    assert result is True
    assert a in b.children


def test_move_node_into_self_rejected():
    tree, a, b, c, d = _build_tree()
    result = tree.move_node(b.id, b.id, 0)
    assert result is False


def test_move_node_into_descendant_rejected():
    tree, a, b, c, d = _build_tree()
    result = tree.move_node(b.id, c.id, 0)
    assert result is False


# ── path_to_node ───────────────────────────────────────────────────────────────

def test_path_to_node_direct_child():
    tree, a, b, c, d = _build_tree()
    path = tree.path_to_node(a.id)
    assert path == ["root", a.id]


def test_path_to_node_nested():
    tree, a, b, c, d = _build_tree()
    path = tree.path_to_node(c.id)
    assert path == ["root", b.id, c.id]


def test_path_to_node_unknown_returns_root():
    tree = TodoTree()
    assert tree.path_to_node("ghost") == ["root"]


# ── serialisation ──────────────────────────────────────────────────────────────

def test_to_dict_from_dict_roundtrip():
    tree, a, b, c, d = _build_tree()
    tree.set_done(c.id, True)
    tree.set_expanded(b.id, True)

    restored = TodoTree.from_dict(tree.to_dict())

    assert restored.get_node(a.id).text == "A"
    assert restored.get_node(b.id).expanded is True
    assert restored.get_node(c.id).done is True
    assert restored.get_node(d.id).done is False
    assert [n.id for n in restored.root.children] == [a.id, b.id]
    assert [n.id for n in restored.get_node(b.id).children] == [c.id, d.id]


def test_from_dict_tolerates_missing_expanded():
    """Documents saved before 'expanded' was added must load without error."""
    data = {
        "id": "root",
        "text": "__root__",
        "done": False,
        "children": [
            {"id": "abc", "text": "Task", "done": False, "children": []},
        ],
    }
    tree = TodoTree.from_dict(data)
    assert tree.get_node("abc").expanded is False


def test_to_json_from_json_roundtrip():
    tree, a, b, c, d = _build_tree()
    json_str = tree.to_json()
    restored = TodoTree.from_json(json_str)
    assert restored.get_node(c.id).text == "C"


def test_from_dict_builds_id_map_for_all_nodes():
    tree, a, b, c, d = _build_tree()
    restored = TodoTree.from_dict(tree.to_dict())
    for nid in ("root", a.id, b.id, c.id, d.id):
        assert restored.get_node(nid) is not None


def test_serialise_empty_tree():
    tree = TodoTree.from_dict(EMPTY_TREE)
    assert tree.root.id == "root"
    assert tree.root.children == []
    # Should be able to round-trip without errors.
    TodoTree.from_dict(tree.to_dict())
