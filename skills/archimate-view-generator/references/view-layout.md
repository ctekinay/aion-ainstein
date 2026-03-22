# ArchiMate View Layout Reference

## Standard Element Dimensions

| Element size  | Width | Height | Use case                          |
|---------------|-------|--------|-----------------------------------|
| Default        | 120   | 55     | Most elements                     |
| Wide           | 160   | 55     | Elements with long names          |
| Composite      | 160   | 70     | Groups, collaborations, locations |
| Minimum        | 100   | 45     | When space is tight               |

---

## Grid Layout: Y-Position per Layer (top to bottom)

When a view contains elements from multiple layers, stack layers vertically:

| Layer          | Y start | Notes                            |
|----------------|---------|----------------------------------|
| Motivation     | 20      | Top — goals, drivers, principles |
| Strategy       | 100     | Capabilities, value streams      |
| Business       | 180     | Actors, processes, services      |
| Application    | 260     | Components, services, functions  |
| Technology     | 340     | Nodes, devices, software         |
| Physical       | 420     | Equipment, facilities            |
| Implementation | 500     | Work packages, deliverables      |

When a view only covers **one layer**, start at `y="20"`.

---

## Horizontal Spacing

Place elements left to right. Default gap between elements:

- Element width: 120
- Gap between elements: 40
- X increment: 160

**Starting position:** `x="20"` for the first element.

### Example: 4 elements in a row
```
Element 1: x="20"
Element 2: x="180"
Element 3: x="340"
Element 4: x="500"
```

---

## Multi-Row Layout

When there are more than 5 elements in a single layer, wrap to a new row.
Add `y + 80` for each subsequent row within the same layer.

### Example: 6 application elements (2 rows)
```
Row 1 (y=260): x=20, 180, 340, 500, 660
Row 2 (y=340): x=20, 180
```

---

## Connection Routing

Connections follow the XML structure — the renderer handles routing automatically.
No explicit waypoints are needed in Open Exchange format.

In the `<connection>` element:
- `source` → identifier of the **source `<node>`** in this view (not the element id)
- `target` → identifier of the **target `<node>`** in this view (not the element id)

---

## Viewpoint-Specific Layout Templates

### Application Layer View
Single layer, elements at y=20, left to right.
```
ApplicationComponent(s) at top row
ApplicationService(s) below (y=100)
DataObject(s) at bottom (y=180)
```

### Technology Infrastructure View
```
Node / Device elements at y=20
SystemSoftware at y=100
Artifact(s) at y=180
CommunicationNetwork spanning bottom
```

### Business Process View
```
BusinessActor / BusinessRole at y=20 (left)
BusinessProcess chain at y=20 (center, flowing left to right)
BusinessObject(s) at y=100 (below the processes they access)
BusinessService at y=180
```

### Motivation View
```
Stakeholder at y=20 (left)
Driver at y=20 (right)
Assessment at y=100
Goal(s) at y=180
Principle / Requirement / Constraint at y=260
```

### Layered (Full Stack) View
Follow the standard Y-offsets per layer exactly.
Use the full grid from Motivation (y=20) down to Technology (y=340) or lower.

---

## Node Identifier Convention

Each `<node>` in a view must have its own unique identifier, separate from the element identifier it references.

```
Element identifier: id-appcomp-1
Node identifier:    id-node-view1-appcomp-1
```

Recommended pattern: `id-n-[view-shortname]-[element-shortname]`

---

## ArchiMate Element Visual Shapes (reference only)

These shapes are rendered by viewers — not expressed in Open Exchange XML.
Included here for understanding the visual semantics:

| Shape type  | Element examples                                              |
|-------------|---------------------------------------------------------------|
| Rectangle   | Structural: Actor, Component, Node, Object, DataObject        |
| Rounded     | Behavioral: Process, Function, Service, Event, Interaction    |
| Ellipse     | Value                                                         |
| Motivation  | Goal, Driver, Requirement, Constraint, Principle, Assessment  |

---

## Layer Colors (reference only — not in Open Exchange XML)

| Layer          | Color   | Hex     |
|----------------|---------|---------|
| Motivation     | Purple  | #CCCCFF |
| Strategy       | Wheat   | #F5DEB3 |
| Business       | Yellow  | #FFFFB5 |
| Application    | Cyan    | #B5FFFF |
| Technology     | Green   | #C9E7B7 |
| Physical       | Green   | #C9E7B7 |
| Implementation | Pink    | #FFB5C0 |
