# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Breadcrumb bar showing the current navigation path through the todo hierarchy."""

from PySide.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu
from PySide.QtCore import Qt, Signal, QPoint


# Estimated horizontal padding for a flat crumb button (px). A heuristic —
# real button padding is platform-dependent, but this is close enough for
# the truncation decision. A few pixels of error just means we occasionally
# show one fewer or one more crumb than theoretically optimal.
_CRUMB_PAD = 12


class BreadcrumbWidget(QWidget):
    """
    Displays a clickable breadcrumb trail: Root > Parent > Current.

    When the path is too long to fit the available width, middle crumbs are
    collapsed behind a … button that opens a popup menu. The first crumb
    (Root or document root) and the last crumb (current view root) are always
    shown; only intermediate ancestors are candidates for hiding.
    """

    nodeClicked = Signal(str)  # node_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path_nodes = []   # [(node_id, label), …]
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)
        self.setStyleSheet("background: palette(midlight);")

    def set_path(self, path_nodes):
        """
        path_nodes: list of (node_id: str, label: str) tuples from root to current.
        """
        self._path_nodes = list(path_nodes)
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    # ── measurement helpers ────────────────────────────────────────────────

    def _display(self, label):
        return "Root" if label == "__root__" else label

    def _crumb_px(self, label):
        """Estimated pixel width of a flat button or bold label for label."""
        return self.fontMetrics().horizontalAdvance(self._display(label)) + _CRUMB_PAD

    def _sep_px(self):
        """Pixel width of a ' > ' separator including its stylesheet padding."""
        return self.fontMetrics().horizontalAdvance(" > ") + 4

    # ── layout ────────────────────────────────────────────────────────────

    def _relayout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._path_nodes:
            self._layout.addStretch()
            return

        visible, hidden = self._compute_visible()
        self._render(visible, hidden)

    def _compute_visible(self):
        """
        Decide which nodes to render directly and which to hide behind ….

        Returns (visible, hidden):
          visible – ordered [(node_id, label)] to display as buttons/bold label
          hidden  – ordered [(node_id, label)] for the … popup menu
        """
        nodes = self._path_nodes
        n = len(nodes)

        if n <= 2:
            # Nothing to truncate: at most first + last.
            return list(nodes), []

        sep_w      = self._sep_px()
        ellipsis_w = self.fontMetrics().horizontalAdvance("…") + _CRUMB_PAD
        available  = max(0, self.width() - 12)  # 6 px left + 6 px right margin

        first, last = nodes[0], nodes[-1]
        middle = nodes[1:-1]

        # Minimum committed width: first crumb + separator + last crumb.
        running = self._crumb_px(first[1]) + sep_w + self._crumb_px(last[1])

        shown  = []
        hidden = list(middle)

        for item in middle:
            needed = sep_w + self._crumb_px(item[1])
            # Crumbs that would still be hidden if we include this one.
            remaining_hidden = len(hidden) - 1
            ellipsis_slot = (sep_w + ellipsis_w) if remaining_hidden > 0 else 0
            if running + needed + ellipsis_slot <= available:
                shown.append(item)
                hidden.remove(item)
                running += needed
            else:
                break

        return [first] + shown + [last], hidden

    def _render(self, visible, hidden):
        n = len(visible)
        # The … button (if needed) is inserted after the last non-final crumb.
        ellipsis_after = n - 2

        for i, (node_id, label) in enumerate(visible):
            if i > 0:
                self._add_sep()

            is_current = (i == n - 1 and node_id == self._path_nodes[-1][0])

            if is_current:
                self._layout.addWidget(QLabel(f"<b>{self._display(label)}</b>"))
            else:
                btn = QPushButton(self._display(label))
                btn.setFlat(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet("text-decoration: underline; border: none;")
                btn.clicked.connect(
                    lambda _c, nid=node_id: self.nodeClicked.emit(nid)
                )
                self._layout.addWidget(btn)

            if hidden and i == ellipsis_after:
                self._add_sep()
                self._add_ellipsis(hidden)

        self._layout.addStretch()

    def _add_sep(self):
        sep = QLabel(">")
        sep.setStyleSheet("color: palette(mid); padding: 0 2px;")
        self._layout.addWidget(sep)

    def _add_ellipsis(self, hidden_nodes):
        btn = QPushButton("…")
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("border: none;")
        menu = QMenu(btn)
        for node_id, label in hidden_nodes:
            action = menu.addAction(self._display(label))
            action.triggered.connect(
                lambda _c, nid=node_id: self.nodeClicked.emit(nid)
            )
        btn.clicked.connect(
            lambda _c, m=menu, b=btn: m.exec_(
                b.mapToGlobal(QPoint(0, b.height()))
            )
        )
        self._layout.addWidget(btn)
