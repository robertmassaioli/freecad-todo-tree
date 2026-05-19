# Navigation — Go Into, Breadcrumbs, and Go Up

For large todo trees it is useful to focus on one branch at a time.
TodoTree lets you zoom into any node so it becomes the temporary root of
the view, hiding everything outside that subtree.

<br/>

## Go Into

Select any item and click **Go Into** to make it the root of the current
view. Only that item's descendants are shown; the rest of the tree is
hidden.

This does not change the data — it is a view setting that is saved with
the document so you return to the same focus when you reopen the file.

**Example:**

```
Full tree             After "Go Into" on Engineering
─────────────         ──────────────────────────────
Personal              Root > Engineering
Engineering  ← into     CAD model
  CAD model               PartDesign body
    PartDesign body      Simulation
  Simulation
Shopping list
```

<br/>

## Breadcrumb trail

While zoomed into a subtree, the **breadcrumb bar** at the top of the
panel shows the path from the document root to the current view root:

```
Root  >  Engineering  >  CAD model
```

Click any ancestor in the breadcrumb to jump back to that level
immediately. The breadcrumb resets to `Root` when you reach the top.

<br/>

## Go Up

Click **Go Up** to move the view root one level back up the hierarchy —
the reverse of Go Into. Pressing Go Up repeatedly walks back up to the
document root.

<br/>

## Expand and collapse

Click the arrow next to any item to expand or collapse its children.
Expanded items stay expanded when you navigate in and out of subtrees.
The set of expanded items is saved with the document.

<br/>

## View state persistence

The current view root, the full breadcrumb path, which items are expanded,
and the Show Done toggle are all saved to the `.FCStd` file as **view
state**. They are stored outside the undo stack, so navigating the tree
does not pollute the document's undo history.

When you reopen the file the panel is restored to exactly where you left it.
