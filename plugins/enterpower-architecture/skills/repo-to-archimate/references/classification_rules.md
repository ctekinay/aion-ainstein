# Classification Rules: Repository Artifacts → ArchiMate Elements

Use this reference when mapping `architecture_notes.json` components, infrastructure,
and external services to ArchiMate 3.2 elements and relationships.

For valid `xsi:type` values see `archimate-shared/references/element-types.md`.
For allowed relationships see `archimate-shared/references/allowed-relations.md`.

---

## 1. Component Type → ArchiMate Element Mapping

### Application Services (type: "service")

Each application service maps to **multiple** ArchiMate elements:

| Component pattern | Elements to create | Relationships |
|---|---|---|
| Service with API endpoints | `ApplicationComponent` + `ApplicationService` + `ApplicationInterface` | Component –Assignment→ Service; Interface –Serving→ external consumers |
| Service without API (worker, background job) | `ApplicationComponent` + `ApplicationFunction` | Component –Assignment→ Function |
| Frontend application | `ApplicationComponent` (name suffix: "Frontend" or "UI") | –Serving→ BusinessActor or BusinessRole |
| Library / SDK module | `ApplicationComponent` | –Serving→ consuming ApplicationComponents |
| Message consumer | `ApplicationComponent` + `ApplicationFunction` | Function triggered by ApplicationEvent |

**Naming conventions:**
- `ApplicationComponent`: Use the service name as-is (e.g., "Order Service")
- `ApplicationService`: Append "API" or use the API title (e.g., "Order Service API")
- `ApplicationInterface`: Append "Interface" or use protocol (e.g., "Order REST API", "Order gRPC")
- `ApplicationFunction`: Use the specific behavior name (e.g., "Process Orders", "Send Notifications")

**Documentation (`doc` field):**
- Compose from: language, framework, purpose (from key_classes), API endpoints summary
- Example: "Python/FastAPI service handling order creation, validation, and persistence.
  Exposes REST API with 5 endpoints. Accesses PostgreSQL for order data."

### Infrastructure (type: "database", "cache", "message_queue", etc.)

| Infrastructure type | Elements to create | Relationships |
|---|---|---|
| database (PostgreSQL, MySQL, MongoDB, etc.) | `SystemSoftware` (DB engine) + `Artifact` (physical DB) + one `DataObject` per table/entity | SystemSoftware –Assignment→ Artifact; ApplicationComponent –Access→ DataObject |
| cache (Redis, Memcached) | `SystemSoftware` + `TechnologyService` | TechnologyService –Serving→ ApplicationComponent |
| message_queue (RabbitMQ, Kafka, NATS) | `SystemSoftware` + `CommunicationNetwork` | Flow relationships between connected ApplicationComponents via the CommunicationNetwork |
| reverse_proxy (Nginx, Traefik) | `SystemSoftware` + `TechnologyInterface` | TechnologyInterface –Serving→ ApplicationInterface |
| search (Elasticsearch, OpenSearch) | `SystemSoftware` + `TechnologyService` | TechnologyService –Serving→ ApplicationComponent |
| monitoring (Prometheus, Grafana) | `SystemSoftware` + `TechnologyService` | TechnologyService –Serving→ Node |
| identity (Keycloak, Auth0) | `SystemSoftware` + `ApplicationService` (auth service) | ApplicationService –Serving→ ApplicationComponent |
| object_storage (MinIO, S3) | `SystemSoftware` + `Artifact` | ApplicationComponent –Access→ Artifact |

### External Services (type: "external_service")

| External pattern | Elements to create | Relationships |
|---|---|---|
| SaaS API (Stripe, Twilio, etc.) | `ApplicationComponent` (external) + `ApplicationService` | External ApplicationService –Serving→ internal ApplicationComponent |
| Cloud SDK (AWS, GCP, Azure) | `TechnologyService` (cloud service) | TechnologyService –Serving→ ApplicationComponent |

Mark external elements with documentation noting they are external/third-party.

### Deployment Infrastructure

Only create these elements if Terraform, Helm, or Kubernetes manifests are present:

| Deployment pattern | Elements to create |
|---|---|
| Docker host / VM | `Node` |
| Kubernetes cluster | `Node` (cluster) with nested `SystemSoftware` (k8s) |
| Container per service | `SystemSoftware` (container runtime) –Assignment→ ApplicationComponent |
| Cloud compute (ECS, EC2, Lambda) | `Node` (compute instance) |
| Cloud network (VPC, subnet) | `CommunicationNetwork` |
| CI/CD pipeline | `TechnologyProcess` (optional — only if user requests implementation layer) |

---

## 2. Edge Type → ArchiMate Relationship Mapping

| dep_graph edge type | ArchiMate relationship | Direction |
|---|---|---|
| `data_access` | `Access` (accessType: ReadWrite) | ApplicationComponent → DataObject |
| `api_call` | `Serving` | Target ApplicationService → Source ApplicationComponent |
| `messaging` | `Flow` | ApplicationComponent → ApplicationComponent (via CommunicationNetwork) |
| `external_integration` | `Serving` | External ApplicationService → Internal ApplicationComponent |
| `infrastructure_dependency` | `Serving` | TechnologyService → ApplicationComponent |
| `file_access` | `Access` (accessType: ReadWrite) | ApplicationComponent → Artifact |

**Important: Serving direction.** In ArchiMate, Serving goes from the provider to the
consumer. If Service A calls Service B's API, the relationship is:
`B's ApplicationService –Serving→ A's ApplicationComponent`.

---

## 3. Layer Assignment Rules

| Condition | Layer |
|---|---|
| ApplicationComponent, ApplicationService, ApplicationInterface, DataObject, ApplicationFunction, ApplicationEvent | **Application Layer** |
| Node, Device, SystemSoftware, Artifact, CommunicationNetwork, TechnologyService, TechnologyProcess, TechnologyInterface, Path | **Technology Layer** |
| BusinessActor, BusinessRole, BusinessProcess, BusinessService, BusinessObject | **Business Layer** — only if README/docs explicitly mention business actors or processes |
| Goal, Requirement, Principle, Driver, Stakeholder, Constraint | **Motivation Layer** — only if ADRs, requirements docs, or principles docs are present |
| WorkPackage, Deliverable, Plateau, Gap | **Implementation Layer** — only if user specifically requests migration/roadmap modeling |

**Default scope:** For a typical code repository, the output model should contain
**Application Layer and Technology Layer** elements. Only add Business/Motivation/Implementation
layers when there is explicit evidence in the repo (README describing business processes,
ADR documents, requirements files).

---

## 4. DataObject Generation from Database Schemas

When `data_models` are present in a component:

- Create one `DataObject` per table/entity
- Name: use table name in PascalCase (e.g., "orders" → "Order", "customer_addresses" → "CustomerAddress")
- Documentation: list column names and types
- Create `Access` relationships from the owning ApplicationComponent to each DataObject
- If foreign keys reference tables owned by a different component, create `Association`
  (isDirected: true) between the DataObjects

---

## 5. Common Mistakes to Avoid

1. **Don't create a separate Node per Docker container in development.** Docker containers
   in docker-compose are development convenience — model the application services, not the
   containers. Only model Nodes for production deployment infrastructure (from Terraform/Helm).

2. **Don't model test infrastructure.** Test databases, mock services, and CI runners are
   not part of the architecture model.

3. **Don't create Business Layer elements without evidence.** A code repository rarely
   contains business process definitions. Stick to Application + Technology layers unless
   the README or ADRs explicitly describe business actors and processes.

4. **Don't duplicate elements.** If PostgreSQL appears in both docker-compose AND Terraform,
   create ONE SystemSoftware element. Use the Terraform name for production context.

5. **Don't model internal implementation details as separate components.** Helper modules,
   utility classes, and internal libraries within a service are part of that service's
   ApplicationComponent — they don't get their own elements unless they are independently
   deployable or have their own API.

6. **Don't create relationships that skip layers without justification.** Prefer
   Application→Technology→Infrastructure chains. A BusinessProcess should not directly
   access an Artifact — it should go through ApplicationComponent and DataObject.

7. **Use `doc` on every element.** Documentation is mandatory. Compose from the available
   data: language, framework, class names, endpoint summary, infrastructure role.

---

## 6. ID Conventions

| Element category | ID prefix | Example |
|---|---|---|
| Application elements | `e-app-` | `e-app-order-service`, `e-app-order-api` |
| Technology elements | `e-tech-` | `e-tech-postgres`, `e-tech-redis` |
| Data objects | `e-data-` | `e-data-order`, `e-data-customer` |
| External elements | `e-ext-` | `e-ext-stripe` |
| Business elements | `e-biz-` | `e-biz-customer-actor` |
| Motivation elements | `e-mot-` | `e-mot-scalability-goal` |
| Relationships | `r-` | `r-order-svc-serves-frontend`, `r-order-accesses-db` |

Use kebab-case. Keep IDs short but descriptive. Relationship IDs should hint at
source, target, and type.
