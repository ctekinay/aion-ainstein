# Quick Reference: Input Concept → ArchiMate Element Mapping

Use this table to map common architectural input concepts to their ArchiMate element types.
For valid `xsi:type` values and full layer context, see `element-types.md`.

| Input concept | ArchiMate type |
|---|---|
| Microservice / service | `ApplicationComponent` |
| API / interface | `ApplicationInterface` |
| Database | `DataObject` (app) or `Artifact` (tech) |
| Message queue | `ApplicationComponent` + `Flow` |
| Frontend app | `ApplicationComponent` |
| User / actor | `BusinessActor` or `BusinessRole` |
| Business process | `BusinessProcess` |
| Infrastructure node | `Node` or `Device` |
| Docker / K8s | `SystemSoftware` |
| Network | `CommunicationNetwork` |
| Library / module | `ApplicationComponent` |
| Use case | `ApplicationFunction` or `BusinessFunction` |
| Deployment artifact | `Artifact` |
| Dependency call | `Serving` or `Access` |
| Trigger / event | `ApplicationEvent` or `BusinessEvent` |
| Data flow | `Flow` |
