# ArchiMate 3.2 Allowed Relationships

## Legend
- ✓ = Allowed
- (✓) = Allowed but indirect / via grouping
- blank = Not allowed

## Relationship Type Abbreviations
- C = Composition
- Ag = Aggregation  
- As = Assignment
- R = Realization
- Sv = Serving
- Ac = Access
- In = Influence
- As0 = Association (always allowed between any two elements)
- T = Triggering
- F = Flow
- Sp = Specialization

---

## Key Allowed Relationships by Relationship Type

### Composition (C)
Source contains/composes Target. Source must be same layer or composite element.
- Grouping → any element
- BusinessActor → BusinessActor, BusinessRole, BusinessCollaboration, BusinessInterface
- BusinessCollaboration → BusinessRole, BusinessInterface
- ApplicationComponent → ApplicationComponent, ApplicationCollaboration, ApplicationInterface
- ApplicationCollaboration → ApplicationInterface
- Node → Node, Device, SystemSoftware, TechnologyCollaboration, TechnologyInterface
- Any layer element → same-layer elements

### Aggregation (Ag)
Weaker containment than Composition. Same rules as Composition.

### Assignment (As)
Active structure → Behavior (who performs what)
**Business:**
- BusinessActor → BusinessRole
- BusinessActor/BusinessRole → BusinessProcess, BusinessFunction, BusinessInteraction, BusinessEvent, BusinessService
- BusinessCollaboration → BusinessInteraction
- BusinessInterface → BusinessProcess, BusinessFunction, BusinessService (exposed at interface)

**Application:**
- ApplicationComponent → ApplicationFunction, ApplicationProcess, ApplicationInteraction, ApplicationEvent, ApplicationService
- ApplicationComponent → ApplicationInterface
- ApplicationCollaboration → ApplicationInteraction

**Technology:**
- Node/Device/SystemSoftware → TechnologyFunction, TechnologyProcess, TechnologyInteraction, TechnologyEvent, TechnologyService
- Node → SystemSoftware, Device
- SystemSoftware → TechnologyInterface

### Realization (R)
Lower layer realizes higher layer behavior/structure
- BusinessProcess/Function/Service → BusinessService
- ApplicationComponent → ApplicationService, ApplicationFunction
- ApplicationFunction/Service → BusinessProcess, BusinessFunction, BusinessService
- TechnologyFunction/Service → ApplicationFunction, ApplicationService
- Artifact → DataObject
- DataObject → BusinessObject
- WorkPackage → Deliverable, Plateau
- Plateau → Capability
- CourseOfAction → Capability
- Capability → Outcome, Goal

### Serving (Sv)
B serves A: B provides a service to A
**Cross-layer (most common):**
- ApplicationService/Component/Function → BusinessProcess, BusinessFunction, BusinessRole, BusinessActor, BusinessInterface
- TechnologyService/Node/Function → ApplicationComponent, ApplicationFunction, ApplicationService, ApplicationInterface
- TechnologyService → BusinessProcess, BusinessFunction (indirect)
- BusinessService → BusinessProcess, BusinessRole (peer)
- ApplicationService → ApplicationComponent (peer)

### Access (Ac)
Active element accesses passive element
- BusinessProcess/Function/Actor/Role → BusinessObject, Contract, Representation, Product
- ApplicationFunction/Process/Component → DataObject
- TechnologyFunction/Process/Node → Artifact
- Application elements → BusinessObject (indirect)

### Influence (In)
Motivation element influences another element
- Driver → Goal, Assessment
- Assessment → Goal, Principle, Requirement, Constraint
- Goal → Goal, Requirement, Constraint, Principle
- Principle → Requirement, Constraint
- Requirement → Requirement, Constraint
- Constraint → Requirement
- Stakeholder → Goal, Driver, Assessment
- Any element → Motivation element

### Triggering (T)
Sequential causation between behavior elements (same or different layer)
- BusinessEvent/Process/Function → BusinessEvent, BusinessProcess, BusinessFunction, BusinessInteraction, BusinessService
- ApplicationEvent/Function/Process → ApplicationEvent, ApplicationFunction, ApplicationProcess, ApplicationInteraction, ApplicationService
- TechnologyEvent/Function/Process → TechnologyEvent, TechnologyFunction, TechnologyProcess
- Cross-layer triggering is generally not allowed

### Flow (F)
Information/material flow between behavior elements
- Same rules as Triggering in terms of element types
- Often used for data/message passing between services, processes, components

### Specialization (Sp)
Subtype relationship — any element → same type parent element
- BusinessProcess → BusinessProcess
- ApplicationComponent → ApplicationComponent
- etc. (always same type)

### Association (As0)
**Always allowed between any two elements.** Use when no more specific relationship applies or when direction is unknown. Can be directed (`isDirected="true"`) or undirected.

---

## Cross-Layer Relationships Summary

| From (lower) | To (higher) | Relationship |
|---|---|---|
| ApplicationComponent | BusinessService | Realization |
| ApplicationService | BusinessProcess | Serving |
| ApplicationFunction | BusinessFunction | Serving |
| TechnologyService | ApplicationService | Serving |
| TechnologyFunction | ApplicationFunction | Serving |
| Node | ApplicationComponent | Assignment (hosting) |
| SystemSoftware | ApplicationComponent | Serving |
| Artifact | DataObject | Realization |
| DataObject | BusinessObject | Realization |
| WorkPackage | Deliverable | Realization |

---

## Common Mistakes to Avoid

1. **Serving goes "upward"** — technology serves application, application serves business
2. **Assignment binds actor to behavior** — not actor to actor (use Composition/Association instead)
3. **Realization crosses layers upward** — lower layer realizes higher layer concepts
4. **Access is only for passive objects** — processes/actors access objects, not services
5. **Triggering stays within same layer** — use Association or Flow for cross-layer triggers
6. **Composition = strong ownership** — prefer Aggregation if the child can exist independently
