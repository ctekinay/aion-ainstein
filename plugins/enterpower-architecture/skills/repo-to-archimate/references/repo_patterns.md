# Common Repository Patterns → ArchiMate Blueprints

Use this reference to identify the repo archetype from `architecture_notes.json` and
apply the corresponding ArchiMate modeling pattern.

---

## Pattern 1: Monorepo (Microservices)

**Detection:** `structure_type: "monorepo"`, multiple components with inter-service edges.

**ArchiMate blueprint:**
- One `ApplicationComponent` per service
- One `ApplicationService` per service (if API endpoints exist)
- `ApplicationInterface` per API protocol (REST, gRPC, GraphQL)
- `Serving` relationships between services (consumer → provider direction)
- Shared `SystemSoftware` for databases, caches, queues
- `DataObject` per service's data domain (avoid cross-service data sharing in model unless explicit)
- Optional: `CommunicationNetwork` for service mesh / message bus

**Relationship emphasis:** Inter-service `Serving` and `Flow` relationships are the architectural backbone.

---

## Pattern 2: Monolith

**Detection:** `structure_type: "single-service"` or `"library"`, single component with many classes/modules.

**ArchiMate blueprint:**
- Single top-level `ApplicationComponent` (the application)
- Multiple `ApplicationFunction` elements for major modules/domains (Composition from parent)
- `ApplicationService` for the external API
- `ApplicationInterface` for the API layer
- `DataObject` per ORM model or table
- `SystemSoftware` for the runtime (e.g., "Python/Django Runtime")

**Relationship emphasis:** Internal `Composition` and `Assignment` relationships. External `Serving` for API consumers.

---

## Pattern 3: Three-Tier (Frontend + API + Database)

**Detection:** One frontend component (React/Vue/Angular), one backend API, one database.

**ArchiMate blueprint:**
```
BusinessActor ("End User")
  ← Serving ← ApplicationService ("Frontend UI")
    ← Serving ← ApplicationComponent ("Frontend App")
      ← Serving ← ApplicationService ("Backend API")
        ← Serving ← ApplicationComponent ("Backend Service")
          → Access → DataObject ("Order", "Customer", etc.)
            ← Realization ← Artifact ("orders table")
              ← Assignment ← SystemSoftware ("PostgreSQL")
```

**Relationship emphasis:** Clean layered Serving chain from user to database.

---

## Pattern 4: Event-Driven / Message-Based

**Detection:** Message queue in infrastructure (RabbitMQ, Kafka, NATS), `messaging` edge type.

**ArchiMate blueprint:**
- `ApplicationComponent` per publisher/consumer service
- `SystemSoftware` for the message broker
- `CommunicationNetwork` representing the messaging backbone
- `ApplicationEvent` for key event types (if detectable from code)
- `Flow` relationships between services through the broker
- Avoid direct `Serving` between event producers and consumers — use `Flow` via the broker

**Relationship emphasis:** `Flow` relationships are primary. `Triggering` between ApplicationEvents and ApplicationFunctions.

---

## Pattern 5: Serverless

**Detection:** IaC with Lambda/Cloud Functions resources, no traditional server infrastructure.

**ArchiMate blueprint:**
- `TechnologyService` for the cloud function runtime (e.g., "AWS Lambda")
- `ApplicationFunction` per Lambda/Cloud Function
- `TechnologyService` for API Gateway
- `ApplicationInterface` exposed via API Gateway
- `Node` representing the cloud platform
- `SystemSoftware` → `Assignment` → `ApplicationFunction`

**Relationship emphasis:** `Assignment` from cloud services to functions. `Triggering` between events and functions.

---

## Pattern 6: Library / SDK

**Detection:** `structure_type: "library"`, no Dockerfile, no docker-compose, package manifest only.

**ArchiMate blueprint:**
- Single `ApplicationComponent` (the library)
- `ApplicationInterface` per public API surface (exported modules/classes)
- Internal `ApplicationFunction` elements for major modules (if complex)
- `Composition` from library to sub-modules
- No Technology Layer unless the library has specific runtime requirements

**Relationship emphasis:** `Composition` and `Serving` (interface → consumers).

---

## Pattern 7: Data Pipeline

**Detection:** Presence of Airflow, Spark, dbt, or ETL-related packages. Multiple data sources.

**ArchiMate blueprint:**
- `ApplicationComponent` per pipeline stage (ingestion, transformation, loading)
- `ApplicationProcess` for the overall pipeline flow
- `DataObject` for source and target datasets
- `SystemSoftware` for orchestration engine (Airflow, dbt)
- `Triggering` between pipeline stages
- `Access` for data reads/writes
- `Flow` for data movement

**Relationship emphasis:** `Triggering` chain for pipeline stages. `Access` for data sources/sinks.

---

## Combining Patterns

Real repositories often combine patterns. For example:
- **Monorepo + Event-Driven:** Apply Pattern 1 for service decomposition, Pattern 4 for messaging relationships.
- **Three-Tier + Serverless:** Apply Pattern 3 for the main stack, Pattern 5 for serverless functions on the side.
- **Monolith + Library:** The main application is Pattern 2, with internal libraries following Pattern 6 as sub-components.

The `structure_type` and edge types in `architecture_notes.json` guide which patterns to combine.
