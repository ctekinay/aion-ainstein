# Quick Reference: IEC 62443 Concept → ArchiMate Element Mapping

Use this table to map IEC 62443 security concepts to their ArchiMate element types.
For valid `xsi:type` values and full layer context, see `element-types.md`.

## Simple Mappings

| IEC 62443 concept | ArchiMate type |
|---|---|
| Security Zone | `Grouping` (stereotyped «Security Zone») |
| Conduit | `Path` + `Flow` relationships for data/signals on it |
| Asset (generic) | Any core element (`Node`, `Device`, `ApplicationComponent`, `DataObject`, `Artifact`) |
| IACS component (embedded device) | `Device` |
| IACS component (host device) | `Node` |
| IACS component (network device) | `Node` or `Device` + association to `CommunicationNetwork` |
| IACS component (software application) | `ApplicationComponent` or `SystemSoftware` |
| System Under Consideration (SuC) | `Grouping` (top-level, containing all zones and conduits) |
| Foundational Requirement (FR) | `Goal` (Motivation layer) |
| System Requirement (SR) | `Requirement` realizing an FR `Goal` |
| Requirement Enhancement (RE) | `Requirement` realizing an SR `Requirement` |
| Component Requirement (CR) | `Requirement` realizing an FR `Goal`, realized by `Device` or `TechnologyFunction` |
| Security Level – target (SL-T) | `Property` on zone `Grouping` + `Assessment` for views |
| Security Level – capability (SL-C) | `Property` on component + `Assessment` for views |
| Security Level – achieved (SL-A) | `Property` on zone `Grouping` + `Assessment` for views |
| Security Policy | `Principle` (Motivation layer) |
| Defence-in-Depth principle | `Principle` (Motivation layer) |
| Least Privilege principle | `Principle` (Motivation layer) |
| Threat | `Assessment` (stereotyped «Threat») |
| Threat Agent | `BusinessActor` or `BusinessRole` (stereotyped «Threat Agent») |
| Vulnerability | `Assessment` (stereotyped «Vulnerability»), associated with affected core element |
| Risk | `Assessment` (stereotyped «Risk»), influenced by Threat and Vulnerability |
| Asset Owner | `BusinessActor` + `Stakeholder` (Motivation layer) |
| System Integrator | `BusinessActor` + `Stakeholder` (Motivation layer) |
| Component Supplier | `BusinessActor` + `Stakeholder` (Motivation layer) |
| Risk Assessment process | `BusinessProcess` assigned to a `BusinessRole` |
| Maturity Level | `Property` on `BusinessProcess` or `Capability` |
| Secure Development Lifecycle (SDL) | `BusinessProcess` with sub-processes per phase |
| Data in transit | `DataObject` + `Flow` along a `Path` (conduit) |
| Data at rest | `DataObject` or `Artifact` accessed by a `Node`/`ApplicationComponent` |
| Incident response | `BusinessProcess` (triggered by `BusinessEvent`) |
| Audit / compliance check | `BusinessProcess` producing `Assessment` outputs |
| Network segmentation | `CommunicationNetwork` elements separated by `Path` conduits |
| Purdue Level (0–5) | `Location` or `Grouping` to represent hierarchical levels |

## Patterns (multi-element concepts)

### Countermeasure / Compensating Control

A countermeasure is not a requirement on its own — it emerges when existing
requirements (SRs realizing FRs) can no longer be fulfilled. Model it as a chain:

```
Assessment (gap: SL-A < SL-T)
  → influences → Goal (restore FR compliance)
    → realized by → CourseOfAction (decision to act)
      → realized by → implementing element:
          - procedural: BusinessProcess (manual workaround, added verification)
          - technical:  Node, ApplicationComponent, SystemSoftware, etc. (deployed control)
```

The `CourseOfAction` is the pivot element — it links the motivation (why) to the
implementation (what). For technical countermeasures, the implementing element
typically appears in a target `Plateau` delivered by a `WorkPackage`.

### CSMS (Cybersecurity Management System)

The CSMS spans three ArchiMate levels following a capability–service–process pattern:

```
Capability ("Managing Cybersecurity")
  → realized by → BusinessService ("CSMS") — SLAs can be attached here
    → realized by → BusinessProcess (the how: risk reviews, patch mgmt, audits, etc.)
```

Use `Capability` for strategic planning, `BusinessService` for governance with
measurable SLAs, and `BusinessProcess` for the operational activities that deliver it.

### Security Zone with Target State (Plateau pattern)

While zones are modelled as `Grouping` elements, you can use `Plateau` to represent
a zone's target security posture for migration planning:

```
Plateau ("Zone X at SL-3")
  └─ contains:
       Grouping ("Zone X") — the zone with its assets (Nodes, Devices, etc.)
       Requirement (SR 1.1, SR 2.1, ...) — SRs required for SL-3
       CourseOfAction — countermeasures needed to reach SL-3
       WorkPackage — implementation effort to get there
```

This lets you model the current state (zone at SL-1) and target state (zone at SL-3)
as separate Plateaus, with a `Gap` element capturing what needs to change. Useful for
roadmap views showing the migration path from current to target security levels.

### Security Level Vector

IEC 62443 defines the SL of a zone as a vector of seven values, one per FR:
`SL = (SL-FR1, SL-FR2, SL-FR3, SL-FR4, SL-FR5, SL-FR6, SL-FR7)`

Model this as seven `Property` entries on the zone `Grouping`:

```
Grouping ("Production Zone A")
  Property: SL-T-FR1 = 3
  Property: SL-T-FR2 = 3
  Property: SL-T-FR3 = 3
  Property: SL-T-FR4 = 1    ← confidentiality not critical here
  Property: SL-T-FR5 = 2
  Property: SL-T-FR6 = 1
  Property: SL-T-FR7 = 3
```

When you need these values to participate in views (e.g., for risk dashboards),
create a corresponding `Assessment` per FR linked to the zone `Grouping`.
