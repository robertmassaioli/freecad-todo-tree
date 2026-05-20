# Checkbox Hit-Test Bug: Proposal

**Date:** 2026-05-20  
**Status:** Root cause identified — fix is a one-method addition

---

## Symptom

- Clicking the drag handle (left 18 px of a row) toggles the done/not-done state.
- Clicking the visible checkbox does nothing.

---

## Root cause

`_DragHandleDelegate` in `tree_panel.py` overrides `paint()` to shift the
rendering rect right by `HANDLE_WIDTH = 18` before delegating to
`super().paint()`:

```python
shifted = copy.copy(option)
shifted.rect = r.adjusted(HANDLE_WIDTH, 0, 0, 0)
super().paint(painter, shifted, index)
```

This makes the checkbox appear 18 px to the right of its "natural" position.

However, `editorEvent()` is **not** overridden. `QStyledItemDelegate.editorEvent()`
is the method Qt calls for all non-edit mouse interactions including checkbox
clicks. It computes the checkbox hit rect from `option.rect` — the **original,
un-shifted** rect. This creates an 18 px mismatch between where the checkbox is
drawn and where Qt tests for clicks:

| Click position | What Qt tests | Result |
|----------------|---------------|--------|
| x < 18 (grip area) | Checkbox rect (original coords) | Checkbox toggles ✗ |
| x ≈ 18+ (visible checkbox) | Outside original checkbox rect | No action ✗ |

The same mismatch affects the inline editor trigger (double-click to rename),
which is also dispatched through `editorEvent()`.

---

## Fix

Override `editorEvent()` in `_DragHandleDelegate` to apply the same rect shift
as `paint()` before forwarding to the base class. This makes Qt's hit-testing
operate in the same coordinate space as the rendering.

```python
def editorEvent(self, event, model, option, index):
    import copy
    shifted = copy.copy(option)
    shifted.rect = option.rect.adjusted(HANDLE_WIDTH, 0, 0, 0)
    return super().editorEvent(event, model, shifted, index)
```

**One method, four lines of code. No other changes required.**

The shift is identical to the one in `paint()`, so the checkbox hit zone will
exactly match the drawn checkbox position. The same fix automatically corrects
the double-click-to-edit hit zone.

---

## Why nothing else needs to change

- `_DragInitFilter.eventFilter()` already uses `visualRect()` to compute
  `local_x` and checks `local_x < HANDLE_WIDTH` to decide whether a press
  started on the grip. This is correct and unaffected.
- `QTreeView` selection (single click on the row) is handled before the
  delegate's `editorEvent`, so selection is already working correctly.
- `sizeHint()` already adds `HANDLE_WIDTH` to the width hint, so row geometry
  is correct.

---

## File to change

| File | Change |
|------|--------|
| `tree_panel.py` | Add `editorEvent` override to `_DragHandleDelegate` |
