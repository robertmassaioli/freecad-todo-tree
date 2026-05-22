# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Test configuration: wire up PySide6 as 'PySide' and mock FreeCAD so that
addon modules can be imported outside of FreeCAD.
"""

import sys
from unittest.mock import MagicMock

import PySide6
import PySide6.QtCore
import PySide6.QtGui
import PySide6.QtWidgets

sys.modules.setdefault("PySide", PySide6)
sys.modules.setdefault("PySide.QtCore", PySide6.QtCore)
sys.modules.setdefault("PySide.QtGui", PySide6.QtGui)
sys.modules.setdefault("PySide.QtWidgets", PySide6.QtWidgets)

sys.modules.setdefault("FreeCAD", MagicMock())
sys.modules.setdefault("FreeCADGui", MagicMock())

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_fc_object(tree_json=None):
    """Return a MagicMock that looks like a FreeCAD TodoTree FeaturePython object."""
    from freecad.TodoTree.todo_model import EMPTY_TREE
    import json

    fc = MagicMock()
    fc.TreeData = json.dumps(EMPTY_TREE) if tree_json is None else tree_json
    return fc
