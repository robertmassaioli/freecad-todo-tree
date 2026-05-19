# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Breadcrumb bar showing the current navigation path through the todo hierarchy."""

from PySide.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide.QtCore import Qt, Signal


class BreadcrumbWidget(QWidget):
    """
    Displays a clickable breadcrumb trail: Root > Parent > Current
    Ancestor labels are buttons; clicking one emits nodeClicked(node_id).
    The final (current) label is plain text.
    """

    nodeClicked = Signal(str)  # node_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)
        self.setStyleSheet("background: palette(midlight);")

    def set_path(self, path_nodes):
        """
        path_nodes: list of (node_id: str, label: str) tuples from root to current.
        """
        # Remove all existing widgets.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, (node_id, label) in enumerate(path_nodes):
            if i > 0:
                sep = QLabel(">")
                sep.setStyleSheet("color: palette(mid); padding: 0 2px;")
                self._layout.addWidget(sep)

            is_last = (i == len(path_nodes) - 1)
            display = label if label != "__root__" else "Root"

            if is_last:
                lbl = QLabel(f"<b>{display}</b>")
                self._layout.addWidget(lbl)
            else:
                btn = QPushButton(display)
                btn.setFlat(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet("text-decoration: underline; border: none;")
                btn.clicked.connect(lambda _checked, nid=node_id: self.nodeClicked.emit(nid))
                self._layout.addWidget(btn)

        self._layout.addStretch()
