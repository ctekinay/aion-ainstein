# ArchiMate 3.2 Valid Element Types (xsi:type values)

## Motivation Layer
- `Stakeholder`
- `Driver`
- `Assessment`
- `Goal`
- `Outcome`
- `Principle`
- `Requirement`
- `Constraint`
- `Meaning`
- `Value`

## Strategy Layer
- `Resource`
- `Capability`
- `CourseOfAction`
- `ValueStream`

## Business Layer
### Active Structure
- `BusinessActor`
- `BusinessRole`
- `BusinessCollaboration`
- `BusinessInterface`

### Behavior
- `BusinessProcess`
- `BusinessFunction`
- `BusinessInteraction`
- `BusinessEvent`
- `BusinessService`

### Passive Structure
- `BusinessObject`
- `Contract`
- `Representation`
- `Product`

## Application Layer
### Active Structure
- `ApplicationComponent`
- `ApplicationCollaboration`
- `ApplicationInterface`

### Behavior
- `ApplicationFunction`
- `ApplicationInteraction`
- `ApplicationProcess`
- `ApplicationEvent`
- `ApplicationService`

### Passive Structure
- `DataObject`

## Technology Layer
### Active Structure
- `Node`
- `Device`
- `SystemSoftware`
- `TechnologyCollaboration`
- `TechnologyInterface`
- `Path`
- `CommunicationNetwork`

### Behavior
- `TechnologyFunction`
- `TechnologyProcess`
- `TechnologyInteraction`
- `TechnologyEvent`
- `TechnologyService`

### Passive Structure
- `Artifact`

## Physical Layer
- `Equipment`
- `Facility`
- `DistributionNetwork`
- `Material`

## Implementation & Migration Layer
- `WorkPackage`
- `Deliverable`
- `ImplementationEvent`
- `Gap`
- `Plateau`

## Composite
- `Grouping`
- `Location`

## Relationships (xsi:type values for `<relationship>`)
- `Composition`
- `Aggregation`
- `Assignment`
- `Realization`
- `Serving`
- `Access`        (optional attr: `accessType="Read|Write|ReadWrite"`)
- `Influence`     (optional attr: `modifier="+"` or `modifier="-"`)
- `Association`   (optional attr: `isDirected="true"`)
- `Triggering`
- `Flow`
- `Specialization`
- `Junction`      (optional attr: `type="And|Or"`)
