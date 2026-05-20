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
    QAbstractItemView, QSizePolicy, QMenu, QApplication,
    QStyledItemDelegate,
)
from PySide.QtGui import QAction, QKeySequence, QShortcut, QPen
try:
    from PySide.QtGui import QDrag
except ImportError:
    from PySide.QtWidgets import QDrag
from PySide.QtCore import Qt, QModelIndex, QSize, QObject, QEvent
import FreeCAD as _fc

from .breadcrumb_widget import BreadcrumbWidget
from .debug import log, Category
from .filter_proxy import DoneFilterProxy


HANDLE_WIDTH = 18


class _DragHandleDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        import copy
        r = option.rect
        # Draw grip lines first in left HANDLE_WIDTH px.
        painter.save()
        pen = QPen(option.palette.mid().color())
        pen.setWidth(1)
        painter.setPen(pen)
        cx = r.left() + 5
        cy = r.center().y()
        for dy in (-4, 0, 4):
            painter.drawLine(cx, cy + dy, cx + 6, cy + dy)
        painter.restore()
        # Shift the rect so the base delegate's checkbox+text don't overlap the grip.
        shifted = copy.copy(option)
        shifted.rect = r.adjusted(HANDLE_WIDTH, 0, 0, 0)
        super().paint(painter, shifted, index)

    def editorEvent(self, event, model, option, index):
        import copy
        shifted = copy.copy(option)
        shifted.rect = option.rect.adjusted(HANDLE_WIDTH, 0, 0, 0)
        return super().editorEvent(event, model, shifted, index)

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width() + HANDLE_WIDTH, hint.height())


class _DragInitFilter(QObject):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self._drag_from_handle = False
        self._drag_start_pos = None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            idx = self._view.indexAt(event.pos())
            if idx.isValid():
                vis_rect = self._view.visualRect(idx)
                local_x = event.x() - vis_rect.left()
                if local_x < HANDLE_WIDTH:
                    self._drag_from_handle = True
                    self._drag_start_pos = event.pos()
                else:
                    self._drag_from_handle = False
            else:
                self._drag_from_handle = False
            return False

        if event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
            if self._drag_from_handle and self._drag_start_pos is not None:
                dist = (event.pos() - self._drag_start_pos).manhattanLength()
                if dist > QApplication.startDragDistance():
                    index = self._view.indexAt(self._drag_start_pos)
                    if index.isValid():
                        mime = self._view.model().mimeData([index])
                        if mime:
                            drag = QDrag(self._view)
                            drag.setMimeData(mime)
                            self._drag_from_handle = False
                            result = drag.exec_(Qt.MoveAction)
                            if result == 0:
                                log(Category.DRAG_DROP, "DRAG completed: drop was not accepted by target")
                            return True
                    self._drag_from_handle = False
            return False

        if event.type() == QEvent.MouseButtonRelease:
            self._drag_from_handle = False
            return False

        return False


class _ClickLogger(QObject):
    def eventFilter(self, obj, event):
        return False


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
        self._restoring_expansion = False  # guard against feedback loops during restore

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
        self._tree_view.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._tree_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(self._context_menu)
        self._tree_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._tree_view.setAcceptDrops(True)
        self._tree_view.setDropIndicatorShown(True)
        self._tree_view.setDragDropMode(QAbstractItemView.DragDrop)
        self._tree_view.setDefaultDropAction(Qt.MoveAction)
        delegate = _DragHandleDelegate(self._tree_view)
        self._tree_view.setItemDelegate(delegate)
        self._click_logger = _ClickLogger(self)
        self._tree_view.viewport().installEventFilter(self._click_logger)
        self._drag_filter = _DragInitFilter(self._tree_view, self._tree_view)
        self._tree_view.viewport().installEventFilter(self._drag_filter)

        # Update indent/outdent button state when selection changes.
        self._tree_view.selectionModel().currentChanged.connect(
            self._update_indent_actions
        )

        # Persist expansion state whenever the user expands or collapses a node
        # so _on_tree_reset can restore it correctly after undo/redo.
        self._tree_view.expanded.connect(self._on_expansion_changed)
        self._tree_view.collapsed.connect(self._on_expansion_changed)

        # Shift+Return — add sibling item; Ctrl+Return — add child item.
        sc_add = QShortcut(QKeySequence(Qt.SHIFT | Qt.Key_Return), self._tree_view)
        sc_add.setContext(Qt.WidgetShortcut)
        sc_add.activated.connect(self._add_sibling)

        sc_add_kp = QShortcut(QKeySequence(Qt.SHIFT | Qt.Key_Enter), self._tree_view)
        sc_add_kp.setContext(Qt.WidgetShortcut)
        sc_add_kp.activated.connect(self._add_sibling)

        sc_add_child = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Return), self._tree_view)
        sc_add_child.setContext(Qt.WidgetShortcut)
        sc_add_child.activated.connect(self._add_child)

        sc_add_child_kp = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Enter), self._tree_view)
        sc_add_child_kp.setContext(Qt.WidgetShortcut)
        sc_add_child_kp.activated.connect(self._add_child)

        # Tab / Shift+Tab — indent / outdent (scoped to tree view).
        sc_indent = QShortcut(QKeySequence(Qt.Key_Tab), self._tree_view)
        sc_indent.setContext(Qt.WidgetShortcut)
        sc_indent.activated.connect(self._indent_selected)

        sc_outdent = QShortcut(QKeySequence(Qt.Key_Backtab), self._tree_view)
        sc_outdent.setContext(Qt.WidgetShortcut)
        sc_outdent.activated.connect(self._outdent_selected)

        # Enter / numpad Enter — Go Into (descend into selected item).
        # Safe because edit triggers are DoubleClicked only, so Enter does
        # not start inline editing.
        sc_into = QShortcut(QKeySequence(Qt.Key_Return), self._tree_view)
        sc_into.setContext(Qt.WidgetShortcut)
        sc_into.activated.connect(self._navigate_into_selected)

        sc_into_kp = QShortcut(QKeySequence(Qt.Key_Enter), self._tree_view)
        sc_into_kp.setContext(Qt.WidgetShortcut)
        sc_into_kp.activated.connect(self._navigate_into_selected)

        # Backspace — Go Up (ascend one breadcrumb level).
        sc_up = QShortcut(QKeySequence(Qt.Key_Backspace), self._tree_view)
        sc_up.setContext(Qt.WidgetShortcut)
        sc_up.activated.connect(self._navigate_up)

        layout.addWidget(self._tree_view)

    # ── view state persistence ─────────────────────────────────────────────

    def _restore_view_state(self):
        try:
            state = json.loads(self._fc_object.ViewState)
        except (ValueError, AttributeError):
            state = {}

        show_done = state.get("show_done", True)
        breadcrumb_path = state.get("breadcrumb_path", ["root"])

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
        self._restore_expanded_from_model()

    def _save_view_state(self):
        """Write view state to the FreeCAD property outside any transaction."""
        if not self._is_primary:
            return
        state = {
            "current_root_id": self._breadcrumb_path[-1],
            "breadcrumb_path": self._breadcrumb_path,
            "show_done": self._act_show_done.isChecked(),
        }
        # No transaction — view state is intentionally outside the undo stack.
        self._fc_object.ViewState = json.dumps(state)

    def _restore_expanded_from_model(self):
        """Expand every node whose model expanded flag is True."""
        self._restoring_expansion = True
        try:
            def _walk(node):
                if node is self._model._tree.root:
                    for child in node.children:
                        _walk(child)
                    return
                src_idx = self._model.index_for_node(node.id)
                if src_idx.isValid():
                    proxy_idx = self._proxy.mapFromSource(src_idx)
                    if node.expanded:
                        self._tree_view.setExpanded(proxy_idx, True)
                for child in node.children:
                    _walk(child)
            _walk(self._model._tree.root)
        finally:
            self._restoring_expansion = False

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

    def _on_expansion_changed(self, proxy_index):
        if self._restoring_expansion:
            return
        src_idx = self._proxy.mapToSource(proxy_index)
        expanded = self._tree_view.isExpanded(proxy_index)
        self._model.set_node_expanded(src_idx, expanded)

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
            # Mark the new parent (previous sibling) as expanded in the model
            # before the indent flushes, so the expansion is captured in the
            # same undo snapshot as the structural change.
            node = src_idx.internalPointer()
            parent = node._parent if node._parent else self._model._tree.root
            row_n = parent.children.index(node)
            prev_sibling_idx = self._model.index_for_node(parent.children[row_n - 1].id)
            self._model.set_node_expanded(prev_sibling_idx, True)
            self._model.indent_node(src_idx)
            new_idx = self._model.index_for_node(node_id)
            if new_idx.isValid():
                proxy_idx = self._proxy.mapFromSource(new_idx)
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
        self._restore_expanded_from_model()

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
