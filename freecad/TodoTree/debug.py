# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Debug logging toggle for the TodoTree addon.

Set DEBUG = True to enable verbose per-render and per-interaction messages
in the FreeCAD Report View. Leave False in normal use.
"""

DEBUG = False


def log(msg: str) -> None:
    if not DEBUG:
        return
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(f"TodoTree [debug] {msg}\n")
    except Exception:
        print(f"TodoTree [debug] {msg}")
