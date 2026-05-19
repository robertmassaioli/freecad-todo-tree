# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

try:
    import FreeCAD
    FreeCAD.Console.PrintMessage("TodoTree: freecad.TodoTree package imported\n")
except Exception:
    print("TodoTree: freecad.TodoTree package imported (FreeCAD console unavailable)")
