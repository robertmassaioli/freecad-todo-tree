# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Breadcrumb bar showing the current navigation path through the todo hierarchy."""

from PySide.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu
from PySide.QtCore import Qt, Signal, QPoint

from .debug import log, Category


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
        self._last_layout_width = -1  # width at last _relayout(); guards resize loop
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)
        self.setStyleSheet("background: palette(midlight);")

    def set_path(self, path_nodes):
        """
        path_nodes: list of (node_id: str, label: str) tuples from root to current.
        """
        self._path_nodes = list(path_nodes)
        labels = [self._display(lbl) for _, lbl in path_nodes]
        log(Category.BREADCRUMB, f"set_path: {' > '.join(labels)} ({len(path_nodes)} crumbs)")
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_width = self.width()
        if new_width == self._last_layout_width:
            # Adding/removing widgets causes Qt to re-evaluate geometry and fire
            # resizeEvent even when the width hasn't changed. Skip the relayout
            # to break the resulting infinite loop.
            log(Category.BREADCRUMB,
                f"resizeEvent: width unchanged at {new_width}px, skipping relayout")
            return
        log(Category.BREADCRUMB,
            f"resizeEvent: width changed {self._last_layout_width}px → {new_width}px")
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
        self._last_layout_width = self.width()
        old_count = self._layout.count()
        log(Category.BREADCRUMB,
            f"_relayout: clearing {old_count} layout items, widget width={self.width()}px")
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._path_nodes:
            self._layout.addStretch()
            log(Category.BREADCRUMB, "_relayout: path is empty, nothing to render")
            return

        visible, hidden = self._compute_visible()
        log(Category.BREADCRUMB,
            f"_relayout: rendering {len(visible)} visible crumbs, "
            f"{len(hidden)} hidden behind ellipsis")
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

        first_w = self._crumb_px(first[1])
        last_w  = self._crumb_px(last[1])

        # Minimum committed width: first crumb + separator + last crumb.
        running = first_w + sep_w + last_w

        log(Category.BREADCRUMB,
            f"_compute_visible: available={available}px  sep={sep_w}px  ellipsis={ellipsis_w}px  "
            f"first='{self._display(first[1])}'({first_w}px)  "
            f"last='{self._display(last[1])}'({last_w}px)  "
            f"base_running={running}px  middle={[self._display(lbl) for _, lbl in middle]}")

        shown  = []
        hidden = list(middle)

        for item in middle:
            crumb_w = self._crumb_px(item[1])
            needed  = sep_w + crumb_w
            remaining_hidden = len(hidden) - 1
            ellipsis_slot = (sep_w + ellipsis_w) if remaining_hidden > 0 else 0
            fits = (running + needed + ellipsis_slot <= available)
            log(Category.BREADCRUMB,
                f"  crumb '{self._display(item[1])}': width={crumb_w}px  needed={needed}px  "
                f"ellipsis_slot={ellipsis_slot}px  running+needed+slot="
                f"{running + needed + ellipsis_slot}px  fits={fits}")
            if fits:
                shown.append(item)
                hidden.remove(item)
                running += needed
            else:
                break

        log(Category.BREADCRUMB,
            f"_compute_visible result: visible=[{', '.join(self._display(lbl) for _, lbl in [first] + shown + [last])}]  "
            f"hidden=[{', '.join(self._display(lbl) for _, lbl in hidden)}]")

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
        log(Category.BREADCRUMB,
            f"_add_ellipsis: building menu with {len(hidden_nodes)} item(s): "
            f"[{', '.join(self._display(lbl) for _, lbl in hidden_nodes)}]")
        btn = QPushButton("…")
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("border: none;")
        menu = QMenu(btn)
        for node_id, label in hidden_nodes:
            display = self._display(label)
            log(Category.BREADCRUMB, f"  adding menu action: '{display}' (id={node_id})")
            action = menu.addAction(display)
            action.triggered.connect(
                lambda _c, nid=node_id: self.nodeClicked.emit(nid)
            )
        log(Category.BREADCRUMB,
            f"_add_ellipsis: menu has {menu.actions().__len__()} action(s), "
            f"btn id={id(btn):#x}  menu id={id(menu):#x}")
        btn.clicked.connect(
            lambda _c, m=menu, b=btn: (
                log(Category.BREADCRUMB,
                    f"ellipsis clicked: showing menu with {len(m.actions())} action(s)  "
                    f"btn id={id(b):#x}  menu id={id(m):#x}"),
                m.exec_(b.mapToGlobal(QPoint(0, b.height())))
            )
        )
        self._layout.addWidget(btn)
