# Breadcrumb Truncation Proposal

**Date:** 2026-05-22  
**Status:** Proposal — for design decision  
**Related:** Ten Improvements Proposal §9

---

## Problem

`BreadcrumbWidget.set_path()` lays out every crumb in a flat `QHBoxLayout`
with a trailing stretch. When the path is long and the dock panel is narrow,
Qt clips the overflow at the right edge:

```
Root  >  Engineering  >  CAD model  >  PartDesign body  >  Sk  [clipped]
```

The clipped crumb is always the *current* view root — the single most
important label in the bar. The user can neither read it nor click any of the
hidden ancestors.

The bug is structural: `QHBoxLayout` does not shrink or hide children when
space runs out. It simply clips.

---

## Scope and constraints

- **No data model changes.** `TreePanel` holds the full `_breadcrumb_path`
  list and passes it to `set_path()`. That does not change.
- **Change is confined to `BreadcrumbWidget`** (plus trivial callers if the
  constructor signature changes).
- **Clickable ancestor navigation must be preserved** for any crumb that is
  visible. A crumb that is visible but not clickable is worse than before.
- **All three options** below are self-contained rewrites of
  `BreadcrumbWidget`. Whichever is chosen, the public API
  (`set_path(path_nodes)` / `nodeClicked` signal) stays identical so
  `TreePanel` does not need to change.

---

## Option A — Ellipsis collapse with popup menu

```
Root  >  …  >  PartDesign body  >  Sketch
               ├── Engineering      (clickable)
               └── CAD model        (clickable)
```

Middle crumbs that do not fit are hidden and replaced by a single `…`
button. Clicking `…` shows a `QMenu` listing each hidden ancestor. Selecting
one emits `nodeClicked` exactly as a visible button would.

### How it works

On every `resizeEvent` (and after `set_path`), a `_relayout()` method
rebuilds the visible widget set from scratch:

1. Measure the available pixel width: `self.width() - left_margin - right_margin`.
2. Using `QFontMetrics`, compute the *natural width* of each crumb label
   plus its separator. Keep a running total.
3. Always reserve space for the first crumb (Root) and the last crumb
   (current node). Compute their combined width first.
4. Fill in middle crumbs left-to-right until adding the next one would
   overflow. The moment one does not fit, replace *all remaining middle
   crumbs* with a single `…` button and stop.
5. If even Root + `…` + last crumb do not fit, drop Root too and show only
   `…` + last.
6. Clear the layout and insert the chosen widgets in order.

Measuring with `QFontMetrics` rather than querying `widget.sizeHint()` avoids
the layout re-entry problem (measuring laid-out widget sizes can trigger
another `resizeEvent` before the first one is resolved).

### Skeleton

```python
class BreadcrumbWidget(QWidget):
    nodeClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path_nodes = []           # [(node_id, label), ...]
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)
        self.setStyleSheet("background: palette(midlight);")

    def set_path(self, path_nodes):
        self._path_nodes = path_nodes
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        # 1. Clear existing widgets.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._path_nodes:
            return

        fm = self.fontMetrics()
        sep_w = fm.horizontalAdvance(" > ")
        ellipsis_w = fm.horizontalAdvance("…") + 16   # button padding
        available = self.width() - 12                  # 6px margin each side

        # 2. Decide which middle crumbs to show.
        first = self._path_nodes[0]
        last  = self._path_nodes[-1]
        middle = self._path_nodes[1:-1]                # may be empty

        def label_w(label):
            display = label if label != "__root__" else "Root"
            return fm.horizontalAdvance(display) + 16  # button/label padding

        first_w = label_w(first[1])
        last_w  = label_w(last[1])
        base_w  = first_w + sep_w + last_w             # minimum: Root > Leaf

        # Add middle crumbs left-to-right until they stop fitting.
        shown_middle = []
        hidden_middle = list(middle)
        running = base_w

        for node_id, label in middle:
            needed = sep_w + label_w(label)
            # If adding this crumb (plus an ellipsis slot for any remaining)
            # still fits, include it.
            remaining_after = [m for m in hidden_middle if m[0] != node_id]
            ellipsis_needed = (sep_w + ellipsis_w) if remaining_after else 0
            if running + needed + ellipsis_needed <= available:
                shown_middle.append((node_id, label))
                hidden_middle.remove((node_id, label))
                running += needed
            else:
                break  # everything from here on goes into the ellipsis

        # 3. Build widgets.
        nodes_to_render = []
        if len(self._path_nodes) > 1:
            nodes_to_render.append(("crumb", first))
            for item in shown_middle:
                nodes_to_render.append(("crumb", item))
            if hidden_middle:
                nodes_to_render.append(("ellipsis", hidden_middle))
            nodes_to_render.append(("crumb", last))
        else:
            nodes_to_render.append(("crumb", first))

        for i, (kind, data) in enumerate(nodes_to_render):
            if i > 0:
                sep = QLabel(">")
                sep.setStyleSheet("color: palette(mid); padding: 0 2px;")
                self._layout.addWidget(sep)

            if kind == "ellipsis":
                hidden = data
                btn = QPushButton("…")
                btn.setFlat(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet("border: none;")
                menu = QMenu(btn)
                for nid, lbl in hidden:
                    display = lbl if lbl != "__root__" else "Root"
                    action = menu.addAction(display)
                    action.triggered.connect(
                        lambda _checked, n=nid: self.nodeClicked.emit(n)
                    )
                btn.setMenu(menu)
                self._layout.addWidget(btn)

            else:  # "crumb"
                node_id, label = data
                display = label if label != "__root__" else "Root"
                is_last = (data is self._path_nodes[-1])
                if is_last:
                    lbl = QLabel(f"<b>{display}</b>")
                    self._layout.addWidget(lbl)
                else:
                    b = QPushButton(display)
                    b.setFlat(True)
                    b.setCursor(Qt.PointingHandCursor)
                    b.setStyleSheet("text-decoration: underline; border: none;")
                    b.clicked.connect(
                        lambda _checked, nid=node_id: self.nodeClicked.emit(nid)
                    )
                    self._layout.addWidget(b)

        self._layout.addStretch()
```

### Tradeoffs

**Pros**
- Best discoverability: hidden crumbs are reachable via the `…` menu
- Prioritises the most important crumbs (first and last) in all cases
- Familiar pattern (browsers, VS Code, file managers all use this)
- Full label text always visible for shown crumbs — no ambiguous truncation

**Cons**
- Most complex of the three options (~120 lines of new widget code)
- `_relayout()` rebuilds all widgets on every resize, which means many
  `deleteLater()` calls; could cause subtle flicker on rapid resize
- The width-measurement arithmetic is fiddly and needs careful testing at
  boundary widths

**Effort:** Medium (3–4 hours including tests)

---

## Option B — Per-label text elision

```
Root  >  Enginee…  >  CAD mo…  >  PartDe…  >  Sketch
```

All crumbs always remain visible. When the bar is too narrow to fit the full
labels, the middle crumb labels are individually shortened with a trailing `…`
using `QFontMetrics.elidedText()`. The first and last crumbs are never elided.

### How it works

On every `resizeEvent`:

1. Compute the total natural width of all crumbs and separators.
2. If everything fits, render full labels (same as today).
3. If not, compute the deficit. Distribute the available space equally across
   the middle crumbs (there are `n - 2` of them). Each middle crumb gets
   `available_for_middle / (n - 2)` pixels.
4. Call `fm.elidedText(label, Qt.ElideRight, per_crumb_width)` to produce a
   truncated label string like `"Engineering…"`.
5. Rebuild the layout with the elided strings. No popup menu needed.

As an enhancement, a `QToolTip` can be set on each elided button so hovering
shows the full label.

### Skeleton

```python
def _relayout(self):
    while self._layout.count():
        item = self._layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    if not self._path_nodes:
        return

    fm = self.fontMetrics()
    sep_w = fm.horizontalAdvance(" > ")
    available = self.width() - 12
    n = len(self._path_nodes)

    def natural_w(label):
        d = label if label != "__root__" else "Root"
        return fm.horizontalAdvance(d) + 16

    total = sum(natural_w(lbl) for _, lbl in self._path_nodes)
    total += sep_w * (n - 1)

    labels = []
    if total <= available or n <= 2:
        labels = [lbl for _, lbl in self._path_nodes]
    else:
        first_w = natural_w(self._path_nodes[0][1])
        last_w  = natural_w(self._path_nodes[-1][1])
        reserved = first_w + last_w + sep_w * (n - 1)
        per_middle = max(40, (available - reserved) // max(1, n - 2))

        labels = []
        for i, (_, lbl) in enumerate(self._path_nodes):
            display = lbl if lbl != "__root__" else "Root"
            if i == 0 or i == n - 1:
                labels.append(display)
            else:
                labels.append(fm.elidedText(display, Qt.ElideRight, per_middle))

    for i, ((node_id, raw_label), display) in enumerate(
            zip(self._path_nodes, labels)):
        if i > 0:
            sep = QLabel(">")
            sep.setStyleSheet("color: palette(mid); padding: 0 2px;")
            self._layout.addWidget(sep)

        is_last = (i == len(self._path_nodes) - 1)
        display_html = f"<b>{display}</b>" if is_last else display
        full_label = raw_label if raw_label != "__root__" else "Root"

        if is_last:
            lbl = QLabel(display_html)
            self._layout.addWidget(lbl)
        else:
            b = QPushButton(display)
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-decoration: underline; border: none;")
            b.setToolTip(full_label)  # show full label on hover
            b.clicked.connect(
                lambda _checked, nid=node_id: self.nodeClicked.emit(nid)
            )
            self._layout.addWidget(b)

    self._layout.addStretch()
```

### Tradeoffs

**Pros**
- Simplest implementation by a wide margin (~60 lines)
- All ancestor crumbs always clickable — no hidden state
- No popup menu, no layout measurement trickiness
- Tooltips on hover give access to full labels

**Cons**
- Elided labels can be ambiguous: `"CAD mo…"` and `"CAD mo…"` look identical
  if two siblings share a prefix — only the tooltip disambiguates
- The current crumb (last item) keeps its full label, but middle crumbs get
  whatever width is left over, which may be very short at narrow widths
- The visual result looks busier than Option A because every slot is still
  occupied

**Effort:** Low (1–2 hours including tests)

---

## Option C — Left-edge truncation (rightmost crumbs win)

```
…  >  CAD model  >  PartDesign body  >  Sketch
```

The bar always shows as many of the *rightmost* crumbs as will fit, dropping
oldest ancestors from the left. A non-interactive `…` at the far left signals
that the path continues further back, but does not offer a menu. The only way
to navigate to a hidden ancestor is via the existing Go Up button or Backspace.

### How it works

On every `resizeEvent`:

1. Start from the *last* crumb and work backward, accumulating widths.
2. Stop when the next crumb would overflow. Everything not included is
   "hidden to the left".
3. If any crumb was hidden, prepend a `…` label (not a button) before the
   first visible crumb.
4. Render the chosen crumbs in order.

### Skeleton

```python
def _relayout(self):
    while self._layout.count():
        item = self._layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    if not self._path_nodes:
        return

    fm = self.fontMetrics()
    sep_w = fm.horizontalAdvance(" > ")
    ellipsis_w = fm.horizontalAdvance("…") + 8
    available = self.width() - 12

    def natural_w(label):
        d = label if label != "__root__" else "Root"
        return fm.horizontalAdvance(d) + 16

    # Greedily include crumbs from the right until we run out of space.
    chosen = []
    running = 0
    for node_id, label in reversed(self._path_nodes):
        w = natural_w(label) + (sep_w if chosen else 0)
        if running + w > available and chosen:
            break
        chosen.insert(0, (node_id, label))
        running += w

    truncated = (len(chosen) < len(self._path_nodes))
    if truncated:
        lbl = QLabel("…")
        lbl.setStyleSheet("color: palette(mid); padding: 0 4px;")
        self._layout.addWidget(lbl)

    for i, (node_id, label) in enumerate(chosen):
        if i > 0 or truncated:
            sep = QLabel(">")
            sep.setStyleSheet("color: palette(mid); padding: 0 2px;")
            self._layout.addWidget(sep)

        display = label if label != "__root__" else "Root"
        is_last = (i == len(chosen) - 1 and
                   node_id == self._path_nodes[-1][0])

        if is_last:
            w = QLabel(f"<b>{display}</b>")
            self._layout.addWidget(w)
        else:
            b = QPushButton(display)
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-decoration: underline; border: none;")
            b.clicked.connect(
                lambda _checked, nid=node_id: self.nodeClicked.emit(nid)
            )
            self._layout.addWidget(b)

    self._layout.addStretch()
```

### Tradeoffs

**Pros**
- Full label text for all visible crumbs (same as Option A)
- Simpler than Option A: no popup menu, no inside-out selection logic
- Always shows the most contextually relevant crumbs (the recent path)

**Cons**
- Hidden ancestors are *completely inaccessible* via the breadcrumb — the
  only route back is Go Up / Backspace. This is acceptable if those shortcuts
  are well-known, but worse than Options A or B for discoverability
- The non-interactive `…` gives no feedback about what is hidden or how
  many levels are missing

**Effort:** Low-Medium (1–2 hours including tests)

---

## Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| **Mechanism** | Collapse middle crumbs into `…` popup | Elide middle label text | Drop left crumbs, static `…` |
| **Hidden ancestors accessible?** | Yes — via popup menu | Yes — all crumbs remain clickable | No — only via Go Up / Backspace |
| **Label text clarity** | Full text for all visible crumbs | Truncated for middle crumbs | Full text for all visible crumbs |
| **Visual complexity** | Medium (popup on `…`) | Low (inline elision) | Low (static `…`) |
| **Implementation effort** | Medium (3–4 h) | Low (1–2 h) | Low-Medium (1–2 h) |
| **Risk of edge-case bugs** | Higher (width measurement, popup lifetime) | Low | Low |
| **Familiar UX pattern** | Yes (browsers, file managers) | Uncommon | Uncommon |

### Recommendation

**Option A** gives the best user experience and matches the pattern users
already know from every file manager and browser. Its extra complexity is
contained entirely within `BreadcrumbWidget` and is testable in isolation.

**Option B** is the right choice if implementation simplicity matters more
than UX polish — for example, as a fast first pass that can be upgraded to A
later.

**Option C** is worth considering only if the decision is made that the Go Up
/ Backspace shortcuts are the canonical way to navigate backward and the
breadcrumb bar is treated as purely informational rather than interactive.

---

## Testing strategy

Whichever option is chosen, the tests should cover:

| Scenario | What to assert |
|----------|----------------|
| Path fits at full width | All crumbs visible, no ellipsis/elision |
| Path overflows by one crumb | Exactly one ancestor is hidden/elided |
| Path overflows severely (8+ levels, very narrow widget) | First and last crumbs still visible; middle handled per option |
| Single-crumb path (at root) | No separator, no ellipsis |
| Two-crumb path | Root + Current, no middle logic triggered |
| Resize from narrow → wide | Crumbs expand correctly on `resizeEvent` |
| Clicking a visible ancestor | `nodeClicked` emitted with correct node ID |
| (Option A only) Clicking `…` menu item | `nodeClicked` emitted with correct node ID |

These are pure Qt widget tests that can run in the existing `tests/` suite
with a `QApplication` fixture and do not require FreeCAD.
