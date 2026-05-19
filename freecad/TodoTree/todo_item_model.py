# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""QAbstractItemModel wrapping TodoTree. Shared between dock and main view."""

from PySide.QtCore import Qt, Signal, QAbstractItemModel, QModelIndex, QMimeData
from PySide.QtGui import QColor, QFont

from .todo_model import TodoTree
from .debug import log
import json


class TodoItemModel(QAbstractItemModel):
    """
    Wraps a TodoTree. Both the dock widget and main view share one instance
    per document, so mutations in either panel are instantly visible in the other.

    TreeData mutations are wrapped in FreeCAD transactions (undo-tracked).
    ViewState mutations bypass transactions (saved to file, not in undo stack).
    """

    # Emitted after an undo/redo reload so panels can re-apply their navigation.
    treeReset = Signal()

    def __init__(self, tree, fc_object, parent=None):
        super().__init__(parent)
        self._tree = tree
        self._fc_object = fc_object
        self._flushing = False  # True while we are writing TreeData ourselves

    # ── flush guard ────────────────────────────────────────────────────────

    def is_flushing(self):
        return self._flushing

    def _flush_to_property(self):
        self._flushing = True
        try:
            self._fc_object.TreeData = self._tree.to_json()
        finally:
            self._flushing = False

    # ── undo/redo reload ───────────────────────────────────────────────────

    def reload_from_property(self):
        """Rebuild the in-memory tree from the FreeCAD property (after undo/redo)."""
        self.beginResetModel()
        self._tree = TodoTree.from_json(self._fc_object.TreeData)
        self.endResetModel()
        self.treeReset.emit()

    # ── QAbstractItemModel interface ───────────────────────────────────────

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = parent.internalPointer() if parent.isValid() else self._tree.root
        children = parent_node.children
        if 0 <= row < len(children):
            return self.createIndex(row, column, children[row])
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent_node = node._parent
        if parent_node is None or parent_node is self._tree.root:
            return QModelIndex()
        grandparent = parent_node._parent if parent_node._parent else self._tree.root
        try:
            row = grandparent.children.index(parent_node)
        except ValueError:
            return QModelIndex()
        return self.createIndex(row, 0, parent_node)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        node = parent.internalPointer() if parent.isValid() else self._tree.root
        return len(node.children)

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return node.text
        if role == Qt.CheckStateRole:
            log(f"data(CheckStateRole): node={node.text!r} done={node.done!r}")
            # Return plain integers so Qt6's C++ delegate can call toInt() correctly.
            # Returning a Python enum causes Qt6 to always read the state as 0 (Unchecked),
            # making unchecking impossible (it always re-checks the item).
            return 2 if node.done else 0
        if role == Qt.UserRole:
            return node.id
        if node.done:
            if role == Qt.ForegroundRole:
                return QColor("gray")
            if role == Qt.FontRole:
                f = QFont()
                f.setStrikeOut(True)
                return f
        return None

    def setData(self, index, value, role=Qt.EditRole):
        log(f"setData: role={role!r} value={value!r}")
        if not index.isValid():
            log("setData: index invalid, returning False")
            return False
        node = index.internalPointer()
        doc = self._fc_object.Document

        if role == Qt.EditRole:
            text = value.strip() if value else ""
            if not text or text == node.text:
                return False
            doc.openTransaction("Todo: rename item")
            self._tree.set_text(node.id, text)
            self._flush_to_property()
            doc.commitTransaction()
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        if role == Qt.CheckStateRole:
            # value may be a Python enum or a plain int depending on what called setData.
            # bool() works for both: 0/Unchecked → False, 2/Checked → True.
            done = bool(value)
            log(f"setData CheckStateRole: value={value!r} done={done!r} node.done={node.done!r}")
            if done == node.done:
                log("setData CheckStateRole: no change, returning False")
                return False
            doc.openTransaction("Todo: toggle done")
            self._tree.set_done(node.id, done)
            self._flush_to_property()
            doc.commitTransaction()
            self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.ForegroundRole, Qt.FontRole])
            return True

        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        f = (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
             | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
        log(f"flags: {f!r}")
        return f

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeData(self, indexes):
        valid = [i for i in indexes if i.isValid()]
        if not valid:
            return None
        node_id = valid[0].internalPointer().id
        mime = QMimeData()
        mime.setData("application/x-todotree-node",
                     json.dumps({"id": node_id}).encode("utf-8"))
        return mime

    def dropMimeData(self, data, action, row, column, parent):
        if not data.hasFormat("application/x-todotree-node"):
            return False
        try:
            payload = json.loads(bytes(data.data("application/x-todotree-node")).decode("utf-8"))
            node_id = payload["id"]
        except (ValueError, KeyError):
            return False

        node = self._tree.get_node(node_id)
        if node is None:
            return False

        # Determine destination parent node and insert_row.
        if parent.isValid():
            dest_parent_node = parent.internalPointer()
            dest_parent_id = dest_parent_node.id
        else:
            dest_parent_node = self._tree.root
            dest_parent_id = "root"

        if row == -1:
            # Drop onto an item — append as last child.
            insert_row = len(dest_parent_node.children)
        else:
            insert_row = row

        # Guard: cannot move a node into itself or its descendants.
        cur = dest_parent_node
        while cur is not None:
            if cur is node:
                return False
            cur = cur._parent

        old_parent_node = node._parent if node._parent else self._tree.root
        old_parent_id = old_parent_node.id
        src_row = old_parent_node.children.index(node)

        old_parent_idx = (QModelIndex() if old_parent_node is self._tree.root
                          else self.index_for_node(old_parent_id))
        dest_parent_idx = (QModelIndex() if dest_parent_node is self._tree.root
                           else self.index_for_node(dest_parent_id))

        # Compute the beginMoveRows destination argument.
        # For a same-parent move where src_row < insert_row, Qt requires dest = insert_row + 1.
        same_parent = (old_parent_node is dest_parent_node)
        if same_parent and src_row < insert_row:
            bm_dest = insert_row + 1
        else:
            bm_dest = insert_row

        doc = self._fc_object.Document
        doc.openTransaction("Todo: move item")
        ok = self.beginMoveRows(old_parent_idx, src_row, src_row, dest_parent_idx, bm_dest)
        if not ok:
            doc.abortTransaction()
            return False
        moved = self._tree.move_node(node_id, dest_parent_id, insert_row)
        if not moved:
            self.endMoveRows()
            doc.abortTransaction()
            return False
        self._flush_to_property()
        doc.commitTransaction()
        self.endMoveRows()
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return "Todo Items"
        return None

    # ── structural mutations ───────────────────────────────────────────────

    def add_child(self, parent_index, text="New item"):
        """Insert a new child under parent_index (or root if invalid)."""
        if parent_index.isValid():
            parent_node = parent_index.internalPointer()
        else:
            parent_node = self._tree.root
            parent_index = QModelIndex()

        row = len(parent_node.children)
        doc = self._fc_object.Document
        doc.openTransaction("Todo: add item")
        self.beginInsertRows(parent_index, row, row)
        self._tree.add_child(parent_node.id, text)
        self._flush_to_property()
        doc.commitTransaction()
        self.endInsertRows()

        # Return the index of the newly added child so callers can start editing it.
        return self.index(row, 0, parent_index)

    def remove_node(self, index):
        """Remove the node at index and all its descendants."""
        if not index.isValid():
            return
        node = index.internalPointer()
        if node is self._tree.root:
            return
        parent_index = self.parent(index)
        row = index.row()
        doc = self._fc_object.Document
        doc.openTransaction("Todo: delete item")
        self.beginRemoveRows(parent_index, row, row)
        self._tree.remove_node(node.id)
        self._flush_to_property()
        doc.commitTransaction()
        self.endRemoveRows()

    def outdent_node(self, index):
        """
        Move node up one level using beginMoveRows so views update without a full reset.
        The caller must have already verified that the operation is permitted.
        """
        if not index.isValid():
            return
        node = index.internalPointer()
        parent = node._parent
        if parent is None or parent is self._tree.root:
            return

        grandparent = parent._parent  # None means grandparent IS root
        if grandparent is None:
            grandparent = self._tree.root

        row_n = parent.children.index(node)
        row_p = grandparent.children.index(parent)
        dest_row = row_p + 1

        parent_idx = self.index_for_node(parent.id)
        gp_idx = (QModelIndex() if grandparent is self._tree.root
                  else self.index_for_node(grandparent.id))

        doc = self._fc_object.Document
        doc.openTransaction("Todo: outdent item")
        self.beginMoveRows(parent_idx, row_n, row_n, gp_idx, dest_row)
        self._tree.outdent_node(node.id)
        self._flush_to_property()
        doc.commitTransaction()
        self.endMoveRows()

    def indent_node(self, index):
        """
        Move node down one level (under previous sibling) using beginMoveRows.
        The caller must have already verified that the operation is permitted.
        """
        if not index.isValid():
            return
        node = index.internalPointer()
        parent = node._parent
        if parent is None:
            parent = self._tree.root

        row_n = parent.children.index(node)
        if row_n == 0:
            return

        prev_sibling = parent.children[row_n - 1]
        dest_row = len(prev_sibling.children)  # append position, before the move

        source_parent_idx = (QModelIndex() if parent is self._tree.root
                             else self.index_for_node(parent.id))
        dest_parent_idx = self.index_for_node(prev_sibling.id)

        doc = self._fc_object.Document
        doc.openTransaction("Todo: indent item")
        self.beginMoveRows(source_parent_idx, row_n, row_n, dest_parent_idx, dest_row)
        self._tree.indent_node(node.id)
        self._flush_to_property()
        doc.commitTransaction()
        self.endMoveRows()

    # ── navigation helper ──────────────────────────────────────────────────

    def index_for_node(self, node_id):
        """Return the QModelIndex for node_id by walking the path from root."""
        node = self._tree.get_node(node_id)
        if node is None or node is self._tree.root:
            return QModelIndex()

        # Build path from root to node (excluding root itself).
        path = []
        current = node
        while current and current is not self._tree.root:
            path.append(current)
            current = current._parent
        path.reverse()

        parent_idx = QModelIndex()
        for n in path:
            parent_node = n._parent if n._parent else self._tree.root
            try:
                row = parent_node.children.index(n)
            except ValueError:
                return QModelIndex()
            parent_idx = self.index(row, 0, parent_idx)

        return parent_idx
