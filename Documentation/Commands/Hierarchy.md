# <img height='24' src='../../freecad/TodoTree/Resources/Icons/Outdent.svg' /> <img height='24' src='../../freecad/TodoTree/Resources/Icons/Indent.svg' /> Hierarchy — Indent and Outdent

Indent and Outdent let you reorganise the tree structure by moving items
up or down one level in the hierarchy. The item's entire subtree of
children travels with it unchanged.

<br/>

## ← Outdent (raise one level)

Moves the selected item **up one level** — out of its current parent and
into the parent's parent, placed immediately after the former parent.

**Keyboard shortcut:** Shift+Tab (when the tree panel has focus)

**Example:**

```
Before              After outdenting C
──────────────      ──────────────────
A                   A
  B                   B
  C  ← outdent      C        ← now sibling of A
    D                 D      ← travels with C
E                   E
```

**Blocked when:**

-   The item is already a direct child of the root (cannot go higher).
-   The item's parent is the current **Go Into** view root — outdenting
    would move the item outside the visible subtree.

<br/>

## → Indent (lower one level)

Moves the selected item **down one level** — out of its current parent and
appended to the children of its previous sibling.

**Keyboard shortcut:** Tab (when the tree panel has focus)

**Example:**

```
Before              After indenting B
──────────────      ─────────────────
A                   A
B  ← indent           B     ← now child of A
  C                     C   ← travels with B
D                   D
```

**Blocked when:**

-   The item is the **first child** of its parent — there is no previous
    sibling to move under.

<br/>

## Chaining moves

After each indent or outdent the moved item remains selected, so you can
press Tab or Shift+Tab repeatedly to move it multiple levels without
re-selecting.

<br/>

## Undo

Both operations are fully undoable via **Edit → Undo** (Ctrl+Z). Undo
restores the item and all its children to their previous position.
