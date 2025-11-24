---
# AION Document Registry - Centralized Metadata Catalog
# This catalog is source-agnostic and can reference documents from any source
# (local files, GitHub, Confluence, data mesh, etc.)

version: "1.0"
catalog_name: "AION Document Registry"
last_updated: "2025-11-24"
description: "Centralized metadata catalog for all architecture decisions, principles, and policy documents"

# Document entries
documents:
  # ===== Energy System Architecture (ESA) - Architecture Decision Records =====

  - id: "esa-adr-0000"
    title: "Use Markdown Architectural Decision Records"
    type: "adr"
    doc_number: "0000"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0000-use-markdown-architectural-decision-records.md"
    status: "accepted"
    tags: ["adr", "conventions", "documentation"]

  - id: "esa-adr-0001"
    title: "Use Conventions in Writing"
    type: "adr"
    doc_number: "0001"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0001-use-conventions-in-writing.md"
    status: "accepted"
    tags: ["conventions", "documentation"]

  - id: "esa-adr-0002"
    title: "Use DACI for Decision-Making Process"
    type: "adr"
    doc_number: "0002"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0002-use-DACI-for-decision-making-process.md"
    status: "accepted"
    tags: ["daci", "decision-making", "process"]

  - id: "esa-adr-0010"
    title: "Prioritize the Origins of Standardizations"
    type: "adr"
    doc_number: "0010"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0010-prioritize-the-origins-of-standardizations.md"
    status: "accepted"
    tags: ["standards", "prioritization"]

  - id: "esa-adr-0011"
    title: "Use Standard for Business Functions"
    type: "adr"
    doc_number: "0011"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0011-use-standard-for-business-functions.md"
    status: "accepted"
    tags: ["standards", "business-functions"]

  - id: "esa-adr-0012"
    title: "Use CIM (IEC 61970/61968/62325) as Default Domain Language"
    type: "adr"
    doc_number: "0012"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0012-use-CIM-as-default-domain-language.md"
    status: "accepted"
    tags: ["cim", "standards", "domain-model", "iec"]

  - id: "esa-adr-0020"
    title: "Verify Demand Response Products"
    type: "adr"
    doc_number: "0020"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0020-verify-demand-response-products.md"
    status: "accepted"
    tags: ["demand-response", "verification"]

  - id: "esa-adr-0021"
    title: "Use Sign Convention for Current Direction"
    type: "adr"
    doc_number: "0021"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0021-use-sign-convention-for-current-direction.md"
    status: "accepted"
    tags: ["conventions", "energy-flow"]

  - id: "esa-adr-0022"
    title: "Use Priority-Based Scheduling"
    type: "adr"
    doc_number: "0022"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0022-use-priority-based-scheduling.md"
    status: "accepted"
    tags: ["scheduling", "priority"]

  - id: "esa-adr-0023"
    title: "Flexibility Service Provider is Responsible to Acquire Operational Constraints"
    type: "adr"
    doc_number: "0023"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0023-flexibility-service-provider-is-responsible-to-acquire-operational-constraints.md"
    status: "accepted"
    tags: ["flexibility", "constraints", "responsibility"]

  - id: "esa-adr-0024"
    title: "Use Standard for Specifying the Energy Directing Market Domain"
    type: "adr"
    doc_number: "0024"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0024-use-standard-for-specifying-the-energy-directing-market-domain.md"
    status: "accepted"
    tags: ["standards", "market-domain"]

  - id: "esa-adr-0025"
    title: "Unify Demand Response Interfaces via Open Standards"
    type: "adr"
    doc_number: "0025"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0025-unify-demand-response-interfaces-via-open-standards.md"
    status: "accepted"
    tags: ["demand-response", "interfaces", "standards"]

  - id: "esa-adr-0026"
    title: "Ensure Idempotent Exchange of Messages"
    type: "adr"
    doc_number: "0026"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0026-ensure-idempotent-exchange-of-messages.md"
    status: "accepted"
    tags: ["idempotency", "messaging"]

  - id: "esa-adr-0027"
    title: "Use TLS to Secure Data Communication"
    type: "adr"
    doc_number: "0027"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0027-use-TLS-to-secure-data-communication.md"
    status: "accepted"
    tags: ["security", "tls", "encryption"]

  - id: "esa-adr-0028"
    title: "Support Participant-Initiated Invalidation of Operating Constraints"
    type: "adr"
    doc_number: "0028"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0028-support-participant-initiated-invalidation-of-operating-constraints.md"
    status: "accepted"
    tags: ["constraints", "invalidation"]

  - id: "esa-adr-0029"
    title: "Use OAuth 2.0 for Identification, Authentication and Authorization"
    type: "adr"
    doc_number: "0029"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/decisions/0029-use-OAuth-2.0--for-identification-authentication-and-authorization.md"
    status: "accepted"
    tags: ["security", "oauth", "authentication", "authorization"]

  # ===== Energy System Architecture (ESA) - Principles =====

  - id: "esa-principle-0010"
    title: "Eventual Consistency by Design"
    type: "principle"
    doc_number: "0010"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0010-eventual-consistency-by-design.md"
    status: "proposed"
    tags: ["eventual-consistency", "distributed-systems", "cap-theorem"]

  - id: "esa-principle-0011"
    title: "Need to Know"
    type: "principle"
    doc_number: "0011"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0011-data-design-need-to-know.md"
    status: "proposed"
    tags: ["data-design", "security", "access-control"]

  - id: "esa-principle-0012"
    title: "Business-Driven Data Readiness"
    type: "principle"
    doc_number: "0012"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0012-business-driven-data-readyness.md"
    status: "proposed"
    tags: ["data-readiness", "business-driven"]

  - id: "esa-principle-0013"
    title: "Business-Compliant Storage – Cost-Efficient Tiering"
    type: "principle"
    doc_number: "0013"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0013-cost-efficient-tiering.md"
    status: "proposed"
    tags: ["storage", "cost-efficiency", "tiering"]

  - id: "esa-principle-0014"
    title: "Business-Compliant Storage – Decision Context Preservation"
    type: "principle"
    doc_number: "0014"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0014-decision-context-preservation.md"
    status: "proposed"
    tags: ["storage", "context-preservation", "decision-making"]

  - id: "esa-principle-0015"
    title: "Business-Compliant Storage – Derived Data Reproduction"
    type: "principle"
    doc_number: "0015"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0015-derived-data-reproduction.md"
    status: "proposed"
    tags: ["storage", "derived-data", "reproduction"]

  - id: "esa-principle-0016"
    title: "Make Uncertainty Explicit to Strengthen Decisions"
    type: "principle"
    doc_number: "0016"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0016-make-uncertain-explicit.md"
    status: "proposed"
    tags: ["uncertainty", "decision-making"]

  - id: "esa-principle-0017"
    title: "Business Specifications Driven Data Ownership"
    type: "principle"
    doc_number: "0017"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0017-data-ownership.md"
    status: "proposed"
    tags: ["data-ownership", "business-specifications"]

  - id: "esa-principle-0018"
    title: "Inquire at the Source"
    type: "principle"
    doc_number: "0018"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0018-inquire-at-the-source.md"
    status: "proposed"
    tags: ["data-source", "inquiry"]

  - id: "esa-principle-0019"
    title: "Source-Proximate Data Preservation"
    type: "principle"
    doc_number: "0019"
    owner:
      team: "Energy System Architecture"
      team_abbr: "ESA"
      department: "Architecture"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/esa-main-artifacts/doc/principles/0019-source-proximate-data-preservation.md"
    status: "proposed"
    tags: ["data-preservation", "source-proximity"]

  # ===== Data Office (DO) - Principles =====

  - id: "do-principle-0001"
    title: "Data is een Asset"
    type: "principle"
    doc_number: "0001"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0001-data-is-een-asset.md"
    status: "accepted"
    tags: ["data-asset", "data-value"]

  - id: "do-principle-0002"
    title: "Data is Beschikbaar"
    type: "principle"
    doc_number: "0002"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0002-data-is-beschikbaar.md"
    status: "accepted"
    tags: ["data-availability"]

  - id: "do-principle-0003"
    title: "Data is Begrijpelijk"
    type: "principle"
    doc_number: "0003"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0003-data-is-begrijpelijk.md"
    status: "accepted"
    tags: ["data-understandability"]

  - id: "do-principle-0004"
    title: "Data is Betrouwbaar"
    type: "principle"
    doc_number: "0004"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0004-data-is-betrouwbaar.md"
    status: "accepted"
    tags: ["data-reliability", "data-quality"]

  - id: "do-principle-0005"
    title: "Data is Herbruikbaar"
    type: "principle"
    doc_number: "0005"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0005-data-is-herbruikbaar.md"
    status: "accepted"
    tags: ["data-reusability"]

  - id: "do-principle-0006"
    title: "Data is Toegankelijk"
    type: "principle"
    doc_number: "0006"
    owner:
      team: "Data Office"
      team_abbr: "DO"
      department: "Data & Analytics"
      organization: "Alliander"
    source:
      type: "local_file"
      location: "data/do-artifacts/principles/0006-data-is-toegankelijk.md"
    status: "accepted"
    tags: ["data-accessibility"]

---

# About This Catalog

This centralized catalog provides a single source of truth for all architecture and governance documents in the AION system.

## Design Principles

1. **Source-Agnostic**: Documents can come from any source (local files, GitHub, Confluence, data mesh, etc.)
2. **ID-Based**: Each document has a unique ID that doesn't change even if the source location changes
3. **Metadata-Rich**: Full ownership, classification, and lineage information for each document
4. **Extensible**: Easy to add new document types, sources, and metadata fields

## Document ID Convention

- `{team_abbr}-{type}-{number}`
- Examples: `esa-adr-0012`, `do-principle-0001`

## Metadata Fields

- **id**: Unique identifier (immutable)
- **title**: Human-readable title
- **type**: Document type (adr, principle, policy, etc.)
- **doc_number**: Original document number from source
- **owner**: Team ownership information
- **source**: Where the document is located (can change without affecting ID)
- **status**: Current status (proposed, accepted, deprecated, etc.)
- **tags**: Searchable tags for categorization

## Future Extensions

This catalog can be extended to support:
- Multiple source types (GitHub repos, Confluence spaces, SharePoint, etc.)
- Document relationships (supersedes, relates-to, implements, etc.)
- Lifecycle management (version history, approval workflow)
- Access control metadata
- Automated indexing via Indexing Agent
