---
parent: Principles
nav_order: PCP.20
dct:
  identifier: urn:uuid:3c9e7f4d-1b2a-4e6c-9d8f-7a2c5e1b8f34
  title: Sovereign-by-Design
  isVersionOf: ready for acceptance
  issued: 2025-12-02
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-12/0020-sovereign-by-design.html"
  versionInfo: "v1.0.0 (2025-12-02)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Sovereign-by-Design

## Statement  
Digital sovereignty is a non-negotiable design criterion: solutions must prefer sovereign options, ensure portability and exit strategies, and keep data, controls, and critical services within EU jurisdiction by default—even when suite/platform convenience or short-term cost savings suggest otherwise.

## Rationale  
Ranked priorities:  
1. **Resilience and continuity** (avoid dependency that can lead to out-of-service risk)  
2. **Compliance obligations** (EU laws, GDPR, NIS2, AI Act)  
3. **Supplier/geo dependency risk** (tensions, export controls, or unilateral policy changes)  
4. **Strategic autonomy** (reduce lock-in and maintain control over data/models)  
5. **Financial exposure** (risk of existential cost if sovereignty is ignored)  

Sovereignty is not just a TCO factor; it is a risk mitigation imperative. Dependency on non-sovereign platforms can lead to operational disruption or business failure if geopolitical or regulatory conditions change.

## Implications  
- **Architecture gating:** All solution designs include sovereignty checks (data location, legal jurisdiction, supplier dependency, portability, exit strategy).  
- **Portability and open standards:** Favor standards-based interfaces, containerization, infrastructure-as-code, and vendor-neutral abstractions to enable redeployment across sovereign environments.  
- **Exit strategies:** For each critical platform/service, maintain a documented and periodically tested exit plan (data/model export, cutover playbooks, recovery time objectives).  
- **Contractual guarantees:** Include data/model portability clauses, audit rights, termination conditions, and SLAs that enable transition to sovereign alternatives.  
- **Exception management:** If the sovereign option is not yet feasible, use an exception process with risk acceptance, compensating controls, and a time-bound remediation plan to become sovereign-ready as soon as reasonable.  
- **Resilience targets:** Critical services must avoid single-provider or non‑EU dependency; design for multi-region EU capability and failover.  
- **AI-specific capability investment:** Where sovereign AI capabilities are scarce, prioritize internal capability building or partnerships with EU-compliant providers to reduce dependency on non-sovereign AI platforms.  
- **Roadmap for sovereignty:** When full sovereignty cannot be achieved immediately due to resource or market limitations, solutions must include a roadmap to reach sovereign compliance over time, with clear milestones and risk mitigation steps.  
- **Governance:** Architecture reviews will block decisions lacking sovereignty evidence; procurement uses a sovereignty checklist for platform evaluations.  
