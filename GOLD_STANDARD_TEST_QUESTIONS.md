# Gold Standard Test Questions for RAG Evaluation

**Version:** 3.0 (Added route expectations, fullness tests, tightened list queries)
**Total Questions:** 49 → Select 25 for final test set

**Scoring Guide:**
- ✅ Correct: Answer matches expected content
- ⚠️ Partial: Answer is relevant but incomplete/imprecise
- ❌ Wrong: Answer is incorrect or hallucinated
- 🚫 No Answer: System correctly says "I don't know" when appropriate

**Route Legend:**
- `vocab` — Terminology/definition lookup via Vocabulary collection
- `direct_doc` — Specific document fetch by ID (ADR.XXXX, PCP.XXXX)
- `approval` — Approval record extraction (who approved ADR.XXXX)
- `semantic` — Semantic/hybrid search across collection(s)
- `list` — Deterministic listing of all matching documents
- `count` — Deterministic count query
- `multi_hop` — Cross-collection semantic search

---

## Category 1: Vocabulary Definitions (8 questions)

### V1. Simple Definition
**Question:** What is "Demandable Capacity" in energy systems?
**Expected:** The difference between a high and low power limit (from ESA vocabulary)
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Easy

### V2. Dutch Term
**Question:** What does "Afroepbaar Vermogen" mean?
**Expected:** Dutch term for Demandable Capacity/Power - the difference between high and low power limit
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Easy

### V3. AI/ML Vocabulary
**Question:** What is Agentic RAG according to the vocabulary?
**Expected:** Definition from AAIO.ttl AI/ML concepts
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Easy

### V4. Energy Market Term
**Question:** What is the Day-Ahead Market?
**Expected:** Definition from ESA or ENTSOE vocabulary
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Easy

### V5. Regulatory Term
**Question:** What is a Metering Point according to ACER terminology?
**Expected:** Definition from ACER vocabulary
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Medium

### V6. ArchiMate Term
**Question:** What is a Business Actor in ArchiMate?
**Expected:** Definition from archimate.ttl vocabulary
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Medium

### V7. Concept Relationships
**Question:** What concepts are related to "Available Transport Capacity"?
**Expected:** Related/broader/narrower concepts from ESA vocabulary
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Hard

### V8. IEC Standard Term
**Question:** What is defined in the IEC 61970 standard?
**Expected:** Common Information Model (CIM) for energy management systems
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Medium

---

## Category 2: ADR-Specific Questions (10 questions)

### A1. Decision Lookup
**Question:** What decision was made about the domain language standard?
**Expected:** ADR.0012 - Use CIM (IEC 61970/61968/62325) as default domain language, Status: Accepted
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Easy

### A2. Status Query
**Question:** What is the status of ADR.0027 about TLS security?
**Expected:** Accepted (decision date: 2025-11-14)
**Expected route:** `direct_doc`
**Allowed doc_types:** [adr, content]
**Difficulty:** Easy

### A3. Decision Rationale
**Question:** Why was CIM chosen as the default domain language?
**Expected:** Semantic interoperability, reusability, compliance with energy sector standards (IEC 61970/61968/62325)
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A4. Security Decision
**Question:** What authentication and authorization standard was chosen?
**Expected:** ADR.0029 - Use OAuth 2.0 for identification, authentication and authorization
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A5. Decision Drivers
**Question:** What drove the decision to use DACI for decision-making?
**Expected:** Need for clear accountability, structured decision process (ADR.0002)
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A6. Technical Decision
**Question:** What sign convention is used for current direction?
**Expected:** ADR.0021 - Passive Sign Convention for electrical systems
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A7. Message Handling
**Question:** How should message exchange be handled in distributed systems?
**Expected:** ADR.0026 - Ensure idempotent exchange of messages for robustness
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A8. Responsibility Assignment
**Question:** Who is responsible for acquiring operational constraints in flexibility services?
**Expected:** ADR.0023 - Flexibility service provider is responsible
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### A9. ADR Format
**Question:** What format is used for Architectural Decision Records?
**Expected:** ADR.0000 - Markdown ADRs using MADR format
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Easy

### A10. Interface Decision
**Question:** What approach is used for Demand/Response product interfaces?
**Expected:** ADR.0025 - Unified D/R product interface for market and grid coordination via open standards
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Hard

---

## Category 3: Direct-Doc Fullness Tests (3 questions)

These detect truncation and missing-subsection regressions in the direct-doc route.

### F1. ADR.0025 Full Content
**Question:** Tell me about ADR.0025
**Expected:** Answer must include all 4 consequences subsection keywords: **Governance**, **Transparency**, **Testing**, **MFFBAS**. `answer` OR `full_text` length > 800 chars (formatter may cap `answer`; check `full_text` before failing). Must NOT contain "Decision Approval Record List" (DAR leak).
**Expected route:** `direct_doc`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium
**Regression:** Catches the consequences truncation bug (answer cut off at "Supporting guidelines are:")

### F2. ADR.0028 Full Content
**Question:** Tell me about ADR.0028
**Expected:** Answer must include consequences with both **Pros** and **Cons** subsections. Must mention "invalidation", "operating constraints", and "FSP" (Flexibility Service Provider). `answer` OR `full_text` length > 500 chars (formatter may cap `answer`; check `full_text` before failing).
**Expected route:** `direct_doc`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium
**Regression:** Catches Pros/Cons consequences format (## Consequences vs ### Consequences)

### F3. ADR.0025 Approval Record
**Question:** Who approved ADR.0025?
**Expected:** Must return structured approver list with names (Robert-Jan Peters, Laurent van Groningen), roles, and decision "Accepted". Must NOT return the ADR content itself.
**Expected route:** `approval`
**Allowed doc_types:** [adr_approval]
**Difficulty:** Medium
**Regression:** Catches DAR vs content doc confusion

---

## Category 4: Principle Questions (6 questions)

### P1. Principle Lookup
**Question:** What does the principle "Data is een Asset" mean?
**Expected:** Data should be captured carefully, its value utilized, and used responsibly
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Easy

### P2. Data Design Principle
**Question:** What is the "need to know" principle for data design?
**Expected:** PCP.0011 - Data design should follow need-to-know basis
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### P3. Data Quality
**Question:** What principle addresses data reliability?
**Expected:** "Data is betrouwbaar" (PCP.0036) - data quality assurance, fitness for purpose
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### P4. Consistency Principle
**Question:** What does "eventual consistency by design" mean?
**Expected:** PCP.0010 - Systems should be designed to handle eventual consistency
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### P5. Data Security
**Question:** What principle covers data access control?
**Expected:** "Data is toegankelijk" (PCP.0038) - security, access control, compliance, audit trails
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### P6. AI Principle
**Question:** What principle guides energy-efficient AI usage?
**Expected:** PCP.0040 - Energy-efficient AI considerations
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

---

## Category 5: Policy Questions (5 questions)

### PO1. Policy Existence
**Question:** What policy document covers data governance at Alliander?
**Expected:** "Alliander Data en Informatie Governance Beleid"
**Expected route:** `semantic`
**Allowed doc_types:** policy
**Difficulty:** Easy

### PO2. Data Classification
**Question:** What policies exist for classifying data products?
**Expected:** "Beleid voor het classificeren van dataproducten" and tactical classification policy
**Expected route:** `semantic`
**Allowed doc_types:** policy
**Difficulty:** Medium

### PO3. Capability Framework
**Question:** What capability document addresses data integration?
**Expected:** "Capability Data-integratie en Interoperabiliteit"
**Expected route:** `semantic`
**Allowed doc_types:** policy
**Difficulty:** Medium

### PO4. Master Data
**Question:** What policy covers master and reference data management?
**Expected:** "Capability Master en Referentiedata Management"
**Expected route:** `semantic`
**Allowed doc_types:** policy
**Difficulty:** Medium

### PO5. Metadata Management
**Question:** Is there a policy for metadata management at Alliander?
**Expected:** Yes - "Capability Metadata Management"
**Expected route:** `semantic`
**Allowed doc_types:** policy
**Difficulty:** Easy

---

## Category 6: Cross-Domain Questions (5 questions)

### X1. Principles + ADR
**Question:** How do the architecture decisions support the data governance principles?
**Expected:** CIM (ADR.0012) supports "Data is herbruikbaar" (interoperability), TLS (ADR.0027) supports "Data is toegankelijk" (security)
**Expected route:** `multi_hop`
**Allowed doc_types:** [adr, content, principle]
**Difficulty:** Hard

### X2. Vocabulary + ADR
**Question:** How does the CIM standard relate to the energy vocabulary used?
**Expected:** CIM (IEC 61970/61968/62325) provides semantic basis for energy domain terms in IEC vocabularies
**Expected route:** `multi_hop`
**Allowed doc_types:** [adr, content, vocabulary]
**Difficulty:** Hard

### X3. Policy + Principles
**Question:** How does the data classification policy align with governance principles?
**Expected:** Classification supports "Data is toegankelijk" (PCP.0038) for access control
**Expected route:** `multi_hop`
**Allowed doc_types:** [policy, principle, content]
**Difficulty:** Hard

### X4. Security Across Domains
**Question:** What security measures are defined across ADRs and principles?
**Expected:** TLS (ADR.0027), OAuth 2.0 (ADR.0029) + "Data is toegankelijk" principle
**Expected route:** `multi_hop`
**Allowed doc_types:** [adr, content, principle]
**Difficulty:** Hard

### X5. Interoperability Theme
**Question:** How is interoperability addressed across architecture decisions?
**Expected:** CIM (ADR.0012), D/R interfaces (ADR.0025), idempotent messages (ADR.0026)
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Hard

---

## Category 7: Listing Queries (3 questions)

### L1. List Security ADRs
**Question:** List all accepted architecture decisions related to security.
**Expected must include:** ADR.0027 (TLS), ADR.0029 (OAuth 2.0)
**Expected optional:** ADR.0026 (idempotent messages) - only if its text explicitly mentions security
**Expected route:** `list`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

### L2. List Data Governance Principles
**Question:** What are all the data governance principles?
**Expected must include:** Data is een Asset, Data is beschikbaar, Data is begrijpelijk, Data is betrouwbaar, Data is herbruikbaar, Data is toegankelijk (the Dutch "Data is ..." subset)
**Expected optional:** Other principles that mention data governance but are not in the core "Data is ..." set
**Expected route:** `list`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### L3. List Vocabularies
**Question:** What vocabulary standards are available in the system?
**Expected must include:** IEC 61970, IEC 62325, ENTSOE-HEMRM, ACER, ArchiMate
**Expected optional:** ESA, AAIO, and other domain-specific vocabularies
**Expected route:** `list`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Easy

---

## Category 8: Comparative Queries (3 questions)

### C1. Compare Security Standards
**Question:** What's the difference between TLS and OAuth 2.0 in our architecture?
**Expected:** TLS (ADR.0027) secures transport layer communication; OAuth 2.0 (ADR.0029) handles authentication/authorization
**Expected route:** `semantic`
**Allowed doc_types:** [adr, content]
**Difficulty:** Hard

### C2. Compare Data Principles
**Question:** What's the difference between "Data is beschikbaar" and "Data is toegankelijk"?
**Expected:** Beschikbaar = availability/discoverability; Toegankelijk = access control/security
**Expected route:** `semantic`
**Allowed doc_types:** [principle, content]
**Difficulty:** Medium

### C3. Compare Standards
**Question:** What's the difference between IEC 61970 and IEC 62325?
**Expected:** 61970 = Energy Management System API; 62325 = Energy Market communications
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Hard

---

## Category 9: Temporal Queries (1 question)

### T2. Decision Timeline
**Question:** When was the CIM standard decision (ADR.0012) accepted?
**Expected:** Decision date: 2025-10-23
**Expected route:** `direct_doc`
**Allowed doc_types:** [adr, content]
**Difficulty:** Medium

---

## Category 10: Disambiguation Queries (2 questions)

### D1. ESA Disambiguation
**Question:** What is ESA?
**Expected:** Energy System Architecture (the project/group at Alliander), NOT European Space Agency
**Expected route:** `vocab` or `semantic`
**Allowed doc_types:** vocabulary or [adr, content]
**Difficulty:** Medium

### D2. CIM Disambiguation
**Question:** What does CIM stand for in this context?
**Expected:** Common Information Model (IEC 61970/61968/62325), NOT Computer Integrated Manufacturing
**Expected route:** `vocab`
**Allowed doc_types:** vocabulary concepts
**Difficulty:** Medium

---

## Category 11: Negative/Edge Cases (3 questions)

### N1. Non-Existent Topic
**Question:** What is the architecture decision about using GraphQL?
**Expected:** Should indicate no such ADR exists (no hallucination)
**Expected route:** `semantic` (should abstain)
**Allowed doc_types:** [adr, content]
**Difficulty:** Test

### N2. Out of Scope
**Question:** What is Alliander's policy on employee vacation days?
**Expected:** Should indicate this is not in the knowledge base
**Expected route:** `semantic` (should abstain)
**Allowed doc_types:** policy
**Difficulty:** Test

### N3. Non-Existent ADR Number
**Question:** What does ADR.0050 decide?
**Expected:** Should indicate ADR.0050 does not exist (ADRs go up to ~0031)
**Expected route:** `direct_doc` (should abstain)
**Allowed doc_types:** [adr, content]
**Difficulty:** Test

---

## Summary Table

| Category | Count | Easy | Medium | Hard | Test |
|----------|-------|------|--------|------|------|
| Vocabulary | 8 | 4 | 3 | 1 | - |
| ADR | 10 | 3 | 6 | 1 | - |
| Fullness (NEW) | 3 | - | 3 | - | - |
| Principles | 6 | 1 | 5 | - | - |
| Policies | 5 | 2 | 3 | - | - |
| Cross-Domain | 5 | - | - | 5 | - |
| Listing | 3 | 1 | 2 | - | - |
| Comparative | 3 | - | 1 | 2 | - |
| Temporal | 1 | - | 1 | - | - |
| Disambiguation | 2 | - | 2 | - | - |
| Negative/Edge | 3 | - | - | - | 3 |
| **TOTAL** | **49** | **11** | **26** | **9** | **3** |

---

## Recommended Final 25 Selection

### Must Keep - Core Coverage (15)
| ID | Question Topic | Why |
|----|---------------|-----|
| V1 | Demandable Capacity | Basic vocabulary |
| V3 | Agentic RAG | AI vocabulary |
| V8 | IEC 61970 | Standard terminology |
| A1 | CIM decision | Core ADR |
| A3 | CIM rationale | Tests understanding |
| A4 | OAuth 2.0 | Security decision |
| A7 | Idempotent messages | Technical decision |
| F1 | ADR.0025 fullness | Truncation regression |
| P1 | Data is een Asset | Core principle |
| P3 | Data reliability | Quality principle |
| P5 | Data access control | Security principle |
| PO1 | Data governance policy | Core policy |
| PO3 | Data integration | Capability doc |
| L2 | List governance principles | Listing query |
| N1 | GraphQL (non-existent) | Hallucination test |

### Recommended Additions (10)
| ID | Question Topic | Why |
|----|---------------|-----|
| V6 | ArchiMate term | New vocabulary |
| A2 | TLS status | Direct-doc route |
| F2 | ADR.0028 fullness | Pros/Cons regression |
| F3 | ADR.0025 approval | Approval route test |
| P4 | Eventual consistency | Technical principle |
| X1 | ADR + Principles | Cross-domain |
| X4 | Security across domains | Cross-domain |
| C1 | TLS vs OAuth | Comparative |
| D1 | ESA disambiguation | Disambiguation |
| N3 | ADR.0050 (non-existent) | Hallucination test |

### Total: 25 questions covering all categories and routes

---

## Scoring Template

**Doc ID matching:** Accept both canonical and display variants as equivalent:
`ADR.0025` = `ADR.25` = `ADR-0025`; `PCP.0036` = `PCP.36` = `PCP-0036`.
Score Doc IDs OK = Y if the correct document was retrieved regardless of ID format.

| ID | Question | Expected Route | Actual Route | Route OK? | Retrieved Doc ID(s) | Doc IDs OK? | Score | Notes |
|----|----------|---------------|-------------|-----------|---------------------|-------------|-------|-------|
| V1 | Demandable Capacity | `vocab` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| V3 | Agentic RAG | `vocab` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| V8 | IEC 61970 | `vocab` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| A1 | CIM decision | `semantic` | | Y/N | ADR.0012 | Y/N | ✅/⚠️/❌/🚫 | |
| A2 | TLS status | `direct_doc` | | Y/N | ADR.0027 | Y/N | ✅/⚠️/❌/🚫 | |
| A3 | CIM rationale | `semantic` | | Y/N | ADR.0012 | Y/N | ✅/⚠️/❌/🚫 | |
| A4 | OAuth 2.0 | `semantic` | | Y/N | ADR.0029 | Y/N | ✅/⚠️/❌/🚫 | |
| A7 | Idempotent messages | `semantic` | | Y/N | ADR.0026 | Y/N | ✅/⚠️/❌/🚫 | |
| F1 | ADR.0025 fullness | `direct_doc` | | Y/N | ADR.0025 | Y/N | ✅/⚠️/❌/🚫 | Governance, Transparency, Testing, MFFBAS |
| F2 | ADR.0028 fullness | `direct_doc` | | Y/N | ADR.0028 | Y/N | ✅/⚠️/❌/🚫 | Pros, Cons, invalidation |
| F3 | ADR.0025 approval | `approval` | | Y/N | ADR.0025D | Y/N | ✅/⚠️/❌/🚫 | Approver names present |
| P1 | Data is een Asset | `semantic` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| P3 | Data reliability | `semantic` | | Y/N | PCP.0036 | Y/N | ✅/⚠️/❌/🚫 | |
| P4 | Eventual consistency | `semantic` | | Y/N | PCP.0010 | Y/N | ✅/⚠️/❌/🚫 | |
| P5 | Data access control | `semantic` | | Y/N | PCP.0038 | Y/N | ✅/⚠️/❌/🚫 | |
| PO1 | Data governance policy | `semantic` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| PO3 | Data integration | `semantic` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| X1 | ADR + Principles | `multi_hop` | | Y/N | ADR.0012, PCP.0038 | Y/N | ✅/⚠️/❌/🚫 | |
| X4 | Security across domains | `multi_hop` | | Y/N | ADR.0027, ADR.0029 | Y/N | ✅/⚠️/❌/🚫 | |
| C1 | TLS vs OAuth | `semantic` | | Y/N | ADR.0027, ADR.0029 | Y/N | ✅/⚠️/❌/🚫 | |
| L2 | List governance principles | `list` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | All "Data is ..." present |
| D1 | ESA disambiguation | `vocab` | | Y/N | | Y/N | ✅/⚠️/❌/🚫 | |
| N1 | GraphQL (non-existent) | `semantic` | | Y/N | — | Y/N | ✅/⚠️/❌/🚫 | Expect abstention |
| N3 | ADR.0050 (non-existent) | `direct_doc` | | Y/N | — | Y/N | ✅/⚠️/❌/🚫 | Expect abstention |

---

## Metrics to Calculate

After running all tests:

1. **Overall Accuracy:** (✅ + 🚫) / Total
2. **Hallucination Rate:** ❌ on N1-N3 / 3
3. **Per-Category Accuracy:** Breakdown by category
4. **Difficulty Accuracy:** Easy vs Medium vs Hard
5. **Route Accuracy:** Route OK count / Total — identifies routing bugs
6. **Retrieval Accuracy:** Doc IDs OK count / Total — identifies retrieval bugs
7. **Failure Triage:** For each failure, categorize as:
   - **Routing bug:** Route OK = N (fix routing logic)
   - **Retrieval bug:** Route OK = Y, Doc IDs OK = N (fix filters/search)
   - **Formatter bug:** Route OK = Y, Doc IDs OK = Y, Score != ✅ (fix response builder)
