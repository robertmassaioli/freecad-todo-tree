# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Icon and resource path helpers."""

import freecad.TodoTree as _module
from importlib import resources
from os.path import dirname, join

_icons = resources.files(_module) / "Resources/Icons"

paths = {
    "translations": join(dirname(__file__), "Resources", "Translations"),
}


def as_icon(name):
    """Return the filesystem path to Resources/Icons/<name>.svg as a str."""
    icon_file = _icons / (name + ".svg")
    with resources.as_file(icon_file) as path:
        return str(path)
