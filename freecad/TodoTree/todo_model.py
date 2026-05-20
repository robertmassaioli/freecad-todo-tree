# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Pure-Python in-memory tree model and JSON serialization. No FreeCAD or Qt imports."""

import json
import uuid


EMPTY_TREE = {
    "id": "root",
    "text": "__root__",
    "done": False,
    "children": [],
}

EMPTY_VIEW_STATE = {
    "current_root_id": "root",
    "breadcrumb_path": ["root"],
    "expanded_ids": [],
    "show_done": True,
}


class TodoNode:
    __slots__ = ("id", "text", "done", "children", "_parent")

    def __init__(self, node_id, text, done=False):
        self.id = node_id
        self.text = text
        self.done = done
        self.children = []
        self._parent = None


class TodoTree:
    def __init__(self):
        self.root = TodoNode("root", "__root__", False)
        self._id_map = {"root": self.root}

    # ── serialization ──────────────────────────────────────────────────────

    def to_dict(self):
        def _node(n):
            return {
                "id": n.id,
                "text": n.text,
                "done": n.done,
                "children": [_node(c) for c in n.children],
            }
        return _node(self.root)

    @classmethod
    def from_dict(cls, data):
        tree = cls.__new__(cls)
        tree._id_map = {}

        def _node(d, parent=None):
            n = TodoNode(d["id"], d["text"], d.get("done", False))
            n._parent = parent
            tree._id_map[n.id] = n
            n.children = [_node(c, n) for c in d.get("children", [])]
            return n

        tree.root = _node(data)
        return tree

    @classmethod
    def from_json(cls, json_str):
        return cls.from_dict(json.loads(json_str))

    def to_json(self):
        return json.dumps(self.to_dict())

    # ── queries ────────────────────────────────────────────────────────────

    def get_node(self, node_id):
        return self._id_map.get(node_id)

    def path_to_node(self, node_id):
        """Return list of node IDs from root down to node_id (inclusive)."""
        node = self._id_map.get(node_id)
        if node is None:
            return ["root"]
        path = []
        current = node
        while current is not None:
            path.append(current.id)
            current = current._parent
        path.reverse()
        return path

    # ── mutations ──────────────────────────────────────────────────────────

    def add_child(self, parent_id, text):
        parent = self._id_map[parent_id]
        node = TodoNode(str(uuid.uuid4()), text)
        node._parent = parent
        parent.children.append(node)
        self._id_map[node.id] = node
        return node

    def remove_node(self, node_id):
        node = self._id_map.get(node_id)
        if node is None or node is self.root:
            return
        if node._parent:
            node._parent.children.remove(node)
        self._purge_ids(node)

    def set_text(self, node_id, text):
        self._id_map[node_id].text = text

    def set_done(self, node_id, done):
        self._id_map[node_id].done = done

    def outdent_node(self, node_id):
        """
        Raise node one level: remove from parent, insert after parent in grandparent.
        Returns False if already a direct child of root (cannot go higher).
        Children travel with the node unchanged.
        """
        node = self._id_map.get(node_id)
        if node is None:
            return False
        parent = node._parent
        if parent is None or parent is self.root:
            return False
        grandparent = parent._parent  # may be self.root (its _parent is None)
        if grandparent is None:
            grandparent = self.root

        parent.children.remove(node)
        insert_pos = grandparent.children.index(parent) + 1
        grandparent.children.insert(insert_pos, node)
        node._parent = grandparent
        return True

    def indent_node(self, node_id):
        """
        Lower node one level: append to the children of its previous sibling.
        Returns False if the node is the first child of its parent (no previous sibling).
        Children travel with the node unchanged.
        """
        node = self._id_map.get(node_id)
        if node is None:
            return False
        parent = node._parent
        if parent is None:
            parent = self.root

        siblings = parent.children
        idx = siblings.index(node)
        if idx == 0:
            return False

        new_parent = siblings[idx - 1]
        siblings.remove(node)
        new_parent.children.append(node)
        node._parent = new_parent
        return True

    def move_node(self, node_id, new_parent_id, insert_row):
        """
        Move node_id to be the insert_row-th child of new_parent_id.
        Returns False if the move is invalid (unknown IDs or circular).
        """
        node = self._id_map.get(node_id)
        new_parent = self._id_map.get(new_parent_id)
        if node is None or new_parent is None:
            return False
        cur = new_parent
        while cur is not None:
            if cur is node:
                return False
            cur = cur._parent
        old_parent = node._parent if node._parent else self.root
        old_parent.children.remove(node)
        insert_row = max(0, min(insert_row, len(new_parent.children)))
        new_parent.children.insert(insert_row, node)
        node._parent = new_parent
        return True

    def _purge_ids(self, node):
        del self._id_map[node.id]
        for child in node.children:
            self._purge_ids(child)
