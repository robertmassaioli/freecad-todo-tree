# Duplicate TodoTree Objects: Detection and Recovery Proposal

**Date:** 2026-05-20  
**Status:** Proposal — pending implementation decision

---

## Background

A FreeCAD document should contain exactly one TodoTree `FeaturePython` object.
Duplicates arise from prior bugs (the eager-creation issue, mid-restore race
conditions) and are a known failure mode — the `_ClearAllCommand` tooltip even
says "Also cleans up any duplicate TodoTree objects left by earlier versions."

Currently, when duplicates exist:
- `find_todo_object` silently returns the **first** matching object and ignores
  the rest. Which object is "first" depends on FreeCAD's internal object
  ordering and is not user-controllable.
- No warning is shown anywhere in the UI.
- The user's data from any non-first objects is silently inaccessible.

---

## Detection

All options share the same detection logic. Add a helper alongside
`find_todo_object` in `todo_object.py`:

```python
def find_all_todo_objects(doc):
    """Return every TodoTree object in doc (normally exactly one)."""
    return [
        obj for obj in doc.Objects
        if "TreeData" in getattr(obj, "PropertiesList", [])
        and "ViewState" in getattr(obj, "PropertiesList", [])
    ]
```

Detection is triggered in `TodoDockWidget.switch_to_document` (which already
calls `find_todo_object`). Replace that call with `find_all_todo_objects` and
check `len(objects) > 1`.

---

## Option A — Inline warning banner in the dock (non-blocking)

### What the user sees

When duplicates are detected, the dock replaces its normal tree panel with a
warning widget:

```
┌────────────────────────────────────────┐
│ ⚠  Multiple todo lists found (3)       │
│                                         │
│ This document contains more than one   │
│ TodoTree object. Only one can be used. │
│ Please choose how to proceed:          │
│                                         │
│  [Keep first]  [Keep latest]           │
│  [Merge all]   [Clear all]             │
│  [Let me pick...]                      │
└────────────────────────────────────────┘
```

"Keep first" and "Keep latest" are resolved by object creation order (object
Name suffix number). "Merge all" combines all trees (see Merge semantics below).
"Clear all" reuses the existing `_ClearAllCommand` logic. "Let me pick…" opens
the picker dialog from Option C.

After resolution the dock switches to the normal tree panel for the surviving
object.

### Implementation

- Add `_make_duplicate_warning_widget(objects, dock)` in `dock_widget.py`.
- Call it from `switch_to_document` when `len(all_objs) > 1`.
- Each button handler performs its action then calls `switch_to_document` again
  to refresh.

### Pros
- Non-blocking — user can still see the dock, ignore the warning, and fix it
  later.
- Context is visible at all times while the problem persists.
- Low implementation complexity.

### Cons
- The tree panel is not accessible while the warning is shown. User cannot see
  which data is at stake before deciding.
- Buttons like "Keep first"/"Keep latest" give no preview of what will be lost.

---

## Option B — Modal conflict-resolution dialog on document activation

### What the user sees

When duplicates are detected, a `QDialog` opens immediately (blocking). It lists
each duplicate with its object name, item count, and a short tree preview (first
3 top-level items). Radio buttons let the user choose one to keep, or special
actions:

```
┌──────────────────────────────────────────────────────┐
│  Multiple Todo Lists Found                           │
│                                                      │
│  This document contains 3 todo lists. This is       │
│  usually caused by a bug in an earlier version.     │
│  Please choose how to resolve this:                 │
│                                                      │
│  ○ Keep  TodoTree   (12 items: Buy milk, Call…)     │
│  ○ Keep  TodoTree001 (3 items: Fix bug, Write…)     │
│  ○ Keep  TodoTree002 (0 items — empty)              │
│                                                      │
│  ○ Merge all into one list (24 items total)         │
│  ○ Clear all and start fresh                        │
│                                                      │
│  [ Cancel ]                    [ Apply ]            │
└──────────────────────────────────────────────────────┘
```

"Cancel" leaves the document untouched and shows the warning banner (Option A
fallback). "Apply" performs the chosen action.

### Implementation

- Add `DuplicateTodoDialog(objects, parent)` in a new `duplicate_dialog.py`.
- Called from `switch_to_document` when duplicates exist.
- Item count: `len(TodoTree.from_json(obj.TreeData)._id_map) - 1` (minus root).
- Preview: first 3 texts from root children of the deserialized tree.
- Merge action: see Merge semantics below.

### Pros
- User sees exactly what data is at stake before committing.
- Item counts and preview text give enough context to make an informed choice.
- Merge option makes it easy to recover all data from all duplicates.

### Cons
- Blocking dialog interrupts document workflow. If the user just wants to open
  the file quickly, they are forced to resolve this first.
- Slightly more implementation work than Option A.

---

## Option C — Auto-merge on detection with undo support (silent recovery)

### What the user sees

When duplicates are detected, the addon silently merges all trees into one
without any dialog. A single message is printed to the FreeCAD Report View:

```
TodoTree: 3 duplicate todo objects found in 'Unnamed'. 
Merged automatically into one. Use Edit > Undo if this was unexpected.
```

The merge is performed inside a FreeCAD transaction so it can be undone.

### Merge semantics (shared with Options A and B)

Given N duplicate objects each with a tree rooted at their root node:

1. Deserialise each object's `TreeData` into a `TodoTree`.
2. Collect all root children from each tree (preserving UUIDs, text, done,
   expanded, and their subtrees).
3. Concatenate them all as root children of a single new tree.
4. Optionally: if N > 1 and any object had items, wrap each object's children
   under a labelled parent node (`"From TodoTree"`, `"From TodoTree001"`, etc.)
   so the user can tell which came from where.
5. Write this merged tree to the surviving object's `TreeData`.
6. Delete the other N-1 objects.

UUID collisions (same node ID appearing in two objects) are resolved by
generating a new UUID for the duplicate.

### Implementation

- Add `merge_todo_objects(objects, doc)` in `todo_object.py`.
- Call from `switch_to_document` before building the panel.
- Wrap in `doc.openTransaction("Todo: merge duplicate objects")` /
  `doc.commitTransaction()`.

### Pros
- Zero friction — user never sees a dialog.
- Undo makes the merge reversible.
- Preserves all data from all duplicates.

### Cons
- User has no control over whether or how the merge happens.
- Silently changing document structure (even with undo) can be surprising.
- If the user wanted to discard one duplicate, they now have to manually delete
  those items.

---

## Option D — Lightweight object-picker dialog (keep-one only)

### What the user sees

A minimal, quick dialog: no preview, just a `QComboBox` listing the duplicate
object names with their item counts, and three action buttons.

```
┌────────────────────────────────────────┐
│  Multiple Todo Lists Found             │
│                                        │
│  Keep:  [TodoTree (12 items)      ▼]  │
│                                        │
│  [ Clear all ]  [ Cancel ]  [ Keep ]  │
└────────────────────────────────────────┘
```

"Keep" deletes all other objects and uses the selected one. "Clear all" is the
nuclear option. "Cancel" shows the banner (Option A) until the user decides.

### Implementation

- A minimal `QDialog` subclass, no preview widget needed.
- Reuses the `find_all_todo_objects` helper and `_ClearAllCommand` logic.
- No merge support (merge is only available in Option B).

### Pros
- Very low implementation cost.
- Fast to dismiss.

### Cons
- No merge option — user may lose data from the discarded object.
- No data preview — user may accidentally discard the wrong object.
- "Keep latest" heuristic may not help if names aren't informative.

---

## Comparison

| Criterion | A — Banner | B — Modal | C — Auto-merge | D — Picker |
|-----------|-----------|-----------|----------------|------------|
| Blocks workflow | No | Yes | No | Yes |
| Shows data preview | No | Yes | No | Partial |
| Merge option | Yes (button) | Yes (radio) | Always | No |
| Implementation effort | Low | Medium | Low-Medium | Low |
| Risk of data loss | Medium | Low | None | Medium |
| User control | High | High | None | Medium |

---

## Recommendation

**Option B** is the best balance of safety and UX. The modal is shown only once
(on document activation), gives enough information to make an informed choice,
includes merge to prevent data loss, and then gets out of the way permanently.

If blocking-modal behaviour is unacceptable, implement **Option A** (banner)
with the "Let me pick…" button opening the Option B dialog on demand.

**Option C** is a good complement to whichever UI option is chosen — the
auto-merge can serve as the logic behind the "Merge all" button in Options A
and B rather than a standalone silent strategy.

---

## Files to add or change

| File | Change |
|------|--------|
| `todo_object.py` | Add `find_all_todo_objects`, `merge_todo_objects` |
| `dock_widget.py` | Call `find_all_todo_objects` in `switch_to_document`; show warning/dialog when `len > 1` |
| `duplicate_dialog.py` (new) | `DuplicateTodoDialog` for Option B |
| `commands.py` | `_ClearAllCommand` can reuse `merge_todo_objects` for its "also cleans up duplicates" path |
