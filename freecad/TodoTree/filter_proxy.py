# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Proxy models that sit between TodoItemModel and QTreeView.

Proxy chain (source → view):
    TodoItemModel → DoneFilterProxy → TextSearchProxy → QTreeView

DoneFilterProxy hides done items when show_done is False.
TextSearchProxy hides items whose text does not match the search string
(a row is kept if it matches OR if any of its descendants match, so the
tree path to a hit remains navigable). Searching is scoped to the current
view root — items outside it are not searched (Qt's setRootIndex handles
this automatically).
"""

from PySide.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from .debug import log, Category


class DoneFilterProxy(QSortFilterProxyModel):
    """
    When show_done is False, any row whose node has done=True is hidden,
    which also hides all descendants (Qt's default tree-filter behaviour).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._show_done = True

    def set_show_done(self, show):
        if show == self._show_done:
            return
        self._show_done = show
        self.invalidateFilter()

    def show_done(self):
        return self._show_done

    def setData(self, index, value, role=Qt.EditRole):
        return super().setData(index, value, role)

    def supportedDropActions(self):
        return self.sourceModel().supportedDropActions()

    def dropMimeData(self, data, action, row, column, proxy_parent):
        if proxy_parent.isValid():
            src_parent = self.mapToSource(proxy_parent)
        else:
            src_parent = QModelIndex()

        if row == -1:
            src_row = -1
        elif proxy_parent.isValid():
            if row < self.rowCount(proxy_parent):
                src_row_idx = self.mapToSource(self.index(row, 0, proxy_parent))
                src_row = src_row_idx.row()
            else:
                src_row = self.sourceModel().rowCount(src_parent)
        else:
            src_row = row

        if row != src_row:
            log(Category.DRAG_DROP, f"DROP proxy row mapping: proxy row {row} → source row {src_row} (filter active)")
        return self.sourceModel().dropMimeData(data, action, src_row, column, src_parent)

    def filterAcceptsRow(self, source_row, source_parent):
        if self._show_done:
            return True
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        node_id = source_model.data(idx, Qt.UserRole)
        if node_id:
            node = source_model._tree.get_node(node_id)
            if node and node.done:
                return False
        return True


class TextSearchProxy(QSortFilterProxyModel):
    """
    Case-insensitive substring filter. A row is shown if its display text
    contains the search string OR if any descendant row (visible through the
    source proxy) does, so the ancestor path to a match stays navigable.

    When search_text is empty every row passes through (no-op).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""

    def set_search_text(self, text):
        normalised = text.strip().lower()
        if normalised == self._search_text:
            return
        self._search_text = normalised
        self.invalidateFilter()

    @property
    def search_text(self):
        return self._search_text

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._search_text:
            return True
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        return self._row_or_descendant_matches(idx, source_model)

    def _row_or_descendant_matches(self, idx, source_model):
        text = (source_model.data(idx, Qt.DisplayRole) or "").lower()
        if self._search_text in text:
            return True
        for row in range(source_model.rowCount(idx)):
            child = source_model.index(row, 0, idx)
            if self._row_or_descendant_matches(child, source_model):
                return True
        return False
