# <img height='24' src='../../freecad/TodoTree/Resources/Icons/AddItem.svg' /> Add Item

Creates new todo items in the tree. Two variants are available depending
on where in the hierarchy you want the new item to appear.

<br/>

## + Item

Adds a new item at the **same level** as the currently selected item —
that is, as a sibling, inserted after the selection.

If nothing is selected the item is added at the top level of the current
view root (the node you have navigated into, or the document root if you
have not navigated anywhere).

<br/>

## <img height='24' src='../../freecad/TodoTree/Resources/Icons/AddChild.svg' /> + Child

Adds a new item as a **child** of the currently selected item, one level
deeper in the hierarchy.

If nothing is selected the item is added as a child of the current view
root.

After creation the new item's parent is automatically expanded so the
child is immediately visible.

<br/>

## Inline editing

Both commands open the new item in **inline edit mode** immediately. Type
the item's label and press Enter to confirm, or press Escape to cancel
(the item is removed on cancel).

Double-clicking any existing item also opens it in inline edit mode so
you can rename it.

<br/>

## Undo

Adding an item is fully undoable via **Edit → Undo** (Ctrl+Z). The item
disappears and the tree is restored to its previous state.

<br/>

## Delete

Select an item and click **Delete** to remove it and all of its children.
This is also undoable.
