# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
TreePanel — composite widget containing:
  - BreadcrumbWidget (navigation path)
  - QToolBar (add / add-child / delete / navigate-into / show-done toggle)
  - QTreeView (the actual todo tree, filtered by DoneFilterProxy)

Each panel instance maintains its own navigation state (breadcrumb path,
show-done toggle). The underlying TodoItemModel is shared across panels.

The dock widget and the main view each own one TreePanel. Because they share
the model, a change in one is immediately reflected in the other.
"""

import json

from PySide.QtWidgets import (
    QWidget, QVBoxLayout, QToolBar, QTreeView,
    QAbstractItemView, QSizePolicy, QMenu,
)
from PySide.QtGui import QAction, QKeySequence, QShortcut
from PySide.QtCore import Qt, QModelIndex, QSize, QObject, QEvent
import FreeCAD as _fc

from .breadcrumb_widget import BreadcrumbWidget
from .debug import log
from .filter_proxy import DoneFilterProxy


class _ClickLogger(QObject):
    """Event filter that logs mouse presses on the tree view viewport (debug only)."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            from .debug import log
            log(f"viewport click: pos={event.pos().x()},{event.pos().y()} button={event.button()!r}")
        return False  # don't consume the event


class TreePanel(QWidget):
    """
    Reusable panel used by both the dock widget and the main view.
    Navigation state (breadcrumb path, show-done) is per-panel and is
    persisted to the document's ViewState property by the dock panel
    (treated as the primary panel).
    """

    def __init__(self, item_model, fc_object, is_primary=False, parent=None):
        super().__init__(parent)
        self._model = item_model
        self._fc_object = fc_object
        self._is_primary = is_primary  # primary panel writes ViewState on changes
        self._breadcrumb_path = ["root"]  # list of node IDs from root to current view root

        self._proxy = DoneFilterProxy(self)
        self._proxy.setSourceModel(item_model)

        self._setup_ui()
        self._restore_view_state()

        # Reconnect navigation after undo/redo resets the model.
        self._model.treeReset.connect(self._on_tree_reset)

    # ── UI construction ────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._breadcrumb = BreadcrumbWidget(self)
        self._breadcrumb.nodeClicked.connect(self._navigate_to)
        layout.addWidget(self._breadcrumb)

        tb = QToolBar(self)
        tb.setIconSize(QSize(16, 16))
        tb.setMovable(False)

        self._act_add = QAction("+ Item", self)
        self._act_add.setToolTip("Add a new item at the same level as the selection")
        self._act_add.triggered.connect(self._add_sibling)
        tb.addAction(self._act_add)

        self._act_add_child = QAction("+ Child", self)
        self._act_add_child.setToolTip("Add a child item under the selection")
        self._act_add_child.triggered.connect(self._add_child)
        tb.addAction(self._act_add_child)

        self._act_delete = QAction("Delete", self)
        self._act_delete.setToolTip("Delete the selected item and all its children")
        self._act_delete.triggered.connect(self._delete_selected)
        tb.addAction(self._act_delete)

        tb.addSeparator()

        self._act_outdent = QAction("← Outdent", self)
        self._act_outdent.setToolTip("Raise this item one level (Shift+Tab)")
        self._act_outdent.setEnabled(False)
        self._act_outdent.triggered.connect(self._outdent_selected)
        tb.addAction(self._act_outdent)

        self._act_indent = QAction("→ Indent", self)
        self._act_indent.setToolTip("Lower this item one level under its previous sibling (Tab)")
        self._act_indent.setEnabled(False)
        self._act_indent.triggered.connect(self._indent_selected)
        tb.addAction(self._act_indent)

        tb.addSeparator()

        self._act_nav_into = QAction("Go Into", self)
        self._act_nav_into.setToolTip("Make the selected item the root of the view")
        self._act_nav_into.triggered.connect(self._navigate_into_selected)
        tb.addAction(self._act_nav_into)

        self._act_nav_up = QAction("Go Up", self)
        self._act_nav_up.setToolTip("Navigate up one level")
        self._act_nav_up.triggered.connect(self._navigate_up)
        tb.addAction(self._act_nav_up)

        tb.addSeparator()

        self._act_show_done = QAction("Show Done", self)
        self._act_show_done.setCheckable(True)
        self._act_show_done.setChecked(True)
        self._act_show_done.setToolTip("Toggle visibility of completed items")
        self._act_show_done.toggled.connect(self._toggle_show_done)
        tb.addAction(self._act_show_done)

        layout.addWidget(tb)

        self._tree_view = QTreeView(self)
        self._tree_view.setModel(self._proxy)
        self._tree_view.setHeaderHidden(True)
        trigger = QAbstractItemView.DoubleClicked
        log(f"QAbstractItemView.DoubleClicked = {trigger!r}")
        self._tree_view.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._tree_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(self._context_menu)
        self._tree_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._click_logger = _ClickLogger(self)
        self._tree_view.viewport().installEventFilter(self._click_logger)

        # Update indent/outdent button state when selection changes.
        self._tree_view.selectionModel().currentChanged.connect(
            self._update_indent_actions
        )

        # Tab / Shift+Tab keyboard shortcuts, scoped to the tree view.
        sc_indent = QShortcut(QKeySequence(Qt.Key_Tab), self._tree_view)
        sc_indent.setContext(Qt.WidgetShortcut)
        sc_indent.activated.connect(self._indent_selected)

        sc_outdent = QShortcut(QKeySequence(Qt.Key_Backtab), self._tree_view)
        sc_outdent.setContext(Qt.WidgetShortcut)
        sc_outdent.activated.connect(self._outdent_selected)

        layout.addWidget(self._tree_view)

    # ── view state persistence ─────────────────────────────────────────────

    def _restore_view_state(self):
        try:
            state = json.loads(self._fc_object.ViewState)
        except (ValueError, AttributeError):
            state = {}

        show_done = state.get("show_done", True)
        breadcrumb_path = state.get("breadcrumb_path", ["root"])
        expanded_ids = state.get("expanded_ids", [])

        # Validate path: truncate at first missing node.
        tree = self._model._tree
        valid_path = []
        for nid in breadcrumb_path:
            if tree.get_node(nid):
                valid_path.append(nid)
            else:
                break
        if not valid_path:
            valid_path = ["root"]
        self._breadcrumb_path = valid_path

        # Apply show-done without emitting a save (we're just loading).
        self._act_show_done.blockSignals(True)
        self._act_show_done.setChecked(show_done)
        self._act_show_done.blockSignals(False)
        self._proxy.set_show_done(show_done)

        self._apply_root_index()
        self._update_breadcrumb_display()
        self._restore_expanded(expanded_ids)

    def _save_view_state(self):
        """Write view state to the FreeCAD property outside any transaction."""
        if not self._is_primary:
            return
        expanded_ids = self._collect_expanded_ids()
        state = {
            "current_root_id": self._breadcrumb_path[-1],
            "breadcrumb_path": self._breadcrumb_path,
            "expanded_ids": expanded_ids,
            "show_done": self._act_show_done.isChecked(),
        }
        # No transaction — view state is intentionally outside the undo stack.
        self._fc_object.ViewState = json.dumps(state)

    def _collect_expanded_ids(self):
        ids = []
        self._walk_expanded(QModelIndex(), ids)
        return ids

    def _walk_expanded(self, proxy_parent, ids):
        for row in range(self._proxy.rowCount(proxy_parent)):
            proxy_idx = self._proxy.index(row, 0, proxy_parent)
            if self._tree_view.isExpanded(proxy_idx):
                src_idx = self._proxy.mapToSource(proxy_idx)
                node_id = self._model.data(src_idx, Qt.UserRole)
                if node_id:
                    ids.append(node_id)
            self._walk_expanded(proxy_idx, ids)

    def _restore_expanded(self, expanded_ids):
        tree = self._model._tree
        for node_id in expanded_ids:
            if tree.get_node(node_id):
                src_idx = self._model.index_for_node(node_id)
                if src_idx.isValid():
                    proxy_idx = self._proxy.mapFromSource(src_idx)
                    self._tree_view.setExpanded(proxy_idx, True)

    # ── navigation ─────────────────────────────────────────────────────────

    def _apply_root_index(self):
        current_root_id = self._breadcrumb_path[-1]
        if current_root_id == "root":
            self._tree_view.setRootIndex(QModelIndex())
        else:
            src_idx = self._model.index_for_node(current_root_id)
            if src_idx.isValid():
                proxy_idx = self._proxy.mapFromSource(src_idx)
                self._tree_view.setRootIndex(proxy_idx)
            else:
                # Node gone; fall back to root.
                self._breadcrumb_path = ["root"]
                self._tree_view.setRootIndex(QModelIndex())

    def _update_breadcrumb_display(self):
        tree = self._model._tree
        path_nodes = []
        for nid in self._breadcrumb_path:
            node = tree.get_node(nid)
            label = node.text if node else nid
            path_nodes.append((nid, label))
        self._breadcrumb.set_path(path_nodes)

    def _navigate_to(self, node_id):
        """Navigate to node_id (called by breadcrumb click)."""
        # Truncate breadcrumb path to the clicked node.
        if node_id in self._breadcrumb_path:
            idx = self._breadcrumb_path.index(node_id)
            self._breadcrumb_path = self._breadcrumb_path[: idx + 1]
        else:
            self._breadcrumb_path = ["root"]

        self._apply_root_index()
        self._update_breadcrumb_display()
        self._save_view_state()

    def _navigate_into_selected(self):
        proxy_idx = self._tree_view.currentIndex()
        if not proxy_idx.isValid():
            return
        src_idx = self._proxy.mapToSource(proxy_idx)
        node_id = self._model.data(src_idx, Qt.UserRole)
        if not node_id or node_id == "root":
            return
        if node_id not in self._breadcrumb_path:
            self._breadcrumb_path.append(node_id)
        self._apply_root_index()
        self._update_breadcrumb_display()
        self._save_view_state()
        # Clear the stale currentIndex so subsequent Add Item uses the view root.
        self._tree_view.setCurrentIndex(QModelIndex())

    def _navigate_up(self):
        if len(self._breadcrumb_path) > 1:
            self._breadcrumb_path.pop()
            self._apply_root_index()
            self._update_breadcrumb_display()
            self._save_view_state()

    # ── item operations ────────────────────────────────────────────────────

    def _current_source_index(self):
        proxy_idx = self._tree_view.currentIndex()
        if proxy_idx.isValid():
            return self._proxy.mapToSource(proxy_idx)
        return QModelIndex()

    def _current_view_root_index(self):
        """Source model index of the current breadcrumb root (QModelIndex() for tree root)."""
        current_root_id = self._breadcrumb_path[-1]
        if current_root_id == "root":
            return QModelIndex()
        return self._model.index_for_node(current_root_id)

    def _add_sibling(self):
        src_idx = self._current_source_index()
        view_root_idx = self._current_view_root_index()
        # If selected item IS the view root (stale currentIndex after "Go Into"),
        # treat it the same as no selection so we add at the view root level.
        if src_idx.isValid() and src_idx != view_root_idx:
            parent_idx = self._model.parent(src_idx)
        else:
            parent_idx = view_root_idx
        new_idx = self._model.add_child(parent_idx, "New item")
        self._start_edit(new_idx)

    def _add_child(self):
        src_idx = self._current_source_index()
        if not src_idx.isValid():
            # No selection: add as child of the current view root.
            src_idx = self._current_view_root_index()
        new_idx = self._model.add_child(src_idx, "New item")
        if src_idx.isValid():
            proxy_parent = self._proxy.mapFromSource(src_idx)
            self._tree_view.setExpanded(proxy_parent, True)
        self._start_edit(new_idx)

    def _start_edit(self, src_idx):
        if src_idx.isValid():
            proxy_idx = self._proxy.mapFromSource(src_idx)
            self._tree_view.setCurrentIndex(proxy_idx)
            self._tree_view.edit(proxy_idx)

    def _delete_selected(self):
        src_idx = self._current_source_index()
        if src_idx.isValid():
            self._model.remove_node(src_idx)

    def _toggle_show_done(self, checked):
        self._proxy.set_show_done(checked)
        self._save_view_state()

    # ── indent / outdent ───────────────────────────────────────────────────

    def _can_outdent(self, src_idx):
        """True if the node can be raised one level given the current view root."""
        if not src_idx.isValid():
            return False
        node = src_idx.internalPointer()
        parent = node._parent
        if parent is None or parent is self._model._tree.root:
            return False  # already at top level
        # Blocked if parent IS the current view root — would escape the subtree.
        view_root_id = self._breadcrumb_path[-1]
        return parent.id != view_root_id

    def _can_indent(self, src_idx):
        """True if the node has a previous sibling it can move under."""
        if not src_idx.isValid():
            return False
        node = src_idx.internalPointer()
        parent = node._parent if node._parent else self._model._tree.root
        return parent.children.index(node) > 0

    def _update_indent_actions(self, current_proxy=None, _previous=None):
        src_idx = self._current_source_index()
        self._act_outdent.setEnabled(self._can_outdent(src_idx))
        self._act_indent.setEnabled(self._can_indent(src_idx))

    def _outdent_selected(self):
        src_idx = self._current_source_index()
        if self._can_outdent(src_idx):
            self._model.outdent_node(src_idx)
            # Re-select the moved node so the user can chain operations.
            new_idx = self._model.index_for_node(
                self._model.data(src_idx, Qt.UserRole)
            )
            if new_idx.isValid():
                self._tree_view.setCurrentIndex(self._proxy.mapFromSource(new_idx))
            self._update_indent_actions()

    def _indent_selected(self):
        src_idx = self._current_source_index()
        if self._can_indent(src_idx):
            node_id = self._model.data(src_idx, Qt.UserRole)
            self._model.indent_node(src_idx)
            new_idx = self._model.index_for_node(node_id)
            if new_idx.isValid():
                proxy_idx = self._proxy.mapFromSource(new_idx)
                # Expand the new parent so the moved node is visible.
                self._tree_view.setExpanded(self._proxy.parent(proxy_idx), True)
                self._tree_view.setCurrentIndex(proxy_idx)
            self._update_indent_actions()

    # ── context menu ───────────────────────────────────────────────────────

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(self._act_add)
        menu.addAction(self._act_add_child)
        menu.addAction(self._act_delete)
        menu.addSeparator()
        menu.addAction(self._act_outdent)
        menu.addAction(self._act_indent)
        menu.addSeparator()
        menu.addAction(self._act_nav_into)
        menu.addAction(self._act_nav_up)
        menu.addSeparator()
        menu.addAction(self._act_show_done)
        menu.exec_(self._tree_view.viewport().mapToGlobal(pos))

    # ── undo/redo reset handler ────────────────────────────────────────────

    def _on_tree_reset(self):
        """Re-apply navigation state after the model was reset by undo/redo."""
        # Validate breadcrumb path against the new tree state.
        tree = self._model._tree
        valid_path = []
        for nid in self._breadcrumb_path:
            if tree.get_node(nid):
                valid_path.append(nid)
            else:
                break
        if not valid_path:
            valid_path = ["root"]
        self._breadcrumb_path = valid_path

        self._apply_root_index()
        self._update_breadcrumb_display()

        # Re-expand nodes that still exist.
        try:
            state = json.loads(self._fc_object.ViewState)
            self._restore_expanded(state.get("expanded_ids", []))
        except (ValueError, AttributeError):
            pass

    # ── public API for FreeCAD commands ───────────────────────────────────

    def add_item(self):
        self._add_sibling()

    def add_child_item(self):
        self._add_child()

    def delete_item(self):
        self._delete_selected()

    def navigate_into(self):
        self._navigate_into_selected()

    def navigate_up(self):
        self._navigate_up()

    def toggle_show_done(self):
        self._act_show_done.setChecked(not self._act_show_done.isChecked())

    def outdent_item(self):
        self._outdent_selected()

    def indent_item(self):
        self._indent_selected()
