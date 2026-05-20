# ArchiMate 3.2 — Visualization Mapping

Defines the subset of ArchiMate 3.2 types supported by the interactive viewer template (`templates/archimate-viewer/template.jsx`). Use this file when generating `VIEWS` data for the viewer.

For the full ArchiMate 3.2 type inventory see `archim-3.2-element-types.md`. For allowed relationship combinations see `archim-3.2-allowed-relations.md`.

---

## Element types and viewer layer keys

The viewer renders five layers. Map every ArchiMate element to its viewer layer key using the table below. Any type not listed falls back to the closest match — do not invent new types.

| Viewer layer key | ArchiMate element types |
|---|---|
| `motivation` | `Stakeholder`, `Driver`, `Assessment`, `Goal`, `Outcome`, `Principle`, `Requirement`, `Constraint`, `Value`, `Meaning` |
| `strategy` | `Capability`, `Resource`, `CourseOfAction`, `ValueStream` |
| `business` | `BusinessActor`, `BusinessRole`, `BusinessService`, `BusinessProcess`, `BusinessObject`, `BusinessInterface`, `BusinessEvent`, `BusinessFunction`, `Contract`, `Product` |
| `application` | `ApplicationComponent`, `ApplicationService`, `ApplicationInterface`, `ApplicationFunction`, `DataObject` |
| `technology` | `Node`, `SystemSoftware`, `Artifact`, `CommunicationNetwork`, `TechnologyService`, `Device` |

ArchiMate types outside these five layers (Physical, Implementation & Migration, Composite) are not rendered by the viewer template and should be omitted from `VIEWS` data.

---

## Supported relation types

The viewer renders the following relation types. Any unsupported type maps to `Association`.

`Association`, `Serving`, `Composition`, `Aggregation`, `Assignment`, `Realization`, `Triggering`, `Flow`, `Access`, `Influence`, `Specialization`
