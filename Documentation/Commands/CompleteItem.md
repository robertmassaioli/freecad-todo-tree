# Completing Items

TodoTree tracks the done/not-done state of every item independently of
its position in the hierarchy.

<br/>

## Checking an item done

Click the **checkbox** to the left of any item's label to mark it as
done. The item's text immediately changes to **grey strikethrough** so
completed work is visually distinct from remaining tasks.

Click the checkbox again to mark the item not-done and restore its normal
appearance.

Toggling an item's state is undoable via **Edit → Undo** (Ctrl+Z).

<br/>

## Children of a done item

Marking a parent item done does not automatically mark its children done —
each item has an independent state. If you want to complete a whole branch,
mark each item individually.

<br/>

## Show Done toggle

The **Show Done** button in the panel toolbar controls whether completed
items are visible:

-   **Checked (default)** — all items are shown; done items appear with
    grey strikethrough text.

-   **Unchecked** — done items are hidden. When a parent item is done its
    entire subtree is hidden with it.

The toggle state is saved with the document, so when you reopen the file
the panel remembers whether you had done items hidden or visible.

<br/>

## Use case: focusing on remaining work

1.  Work through your tasks, checking each one done as you complete it.
2.  Click **Show Done** to hide all completed items.
3.  The panel now shows only what remains, with no visual clutter from
    finished tasks.
4.  Click **Show Done** again to review the full history.
