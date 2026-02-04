# Gold Standard Test Questions for RAG Evaluation

**Version:** 2.0 (Updated with verified ADR references and new question types)
**Total Questions:** 40 → Select 20-25 for final test set

**Scoring Guide:**
- ✅ Correct: Answer matches expected content
- ⚠️ Partial: Answer is relevant but incomplete/imprecise
- ❌ Wrong: Answer is incorrect or hallucinated
- 🚫 No Answer: System correctly says "I don't know" when appropriate

---

## Category 1: Vocabulary Definitions (8 questions)

### V1. Simple Definition
**Question:** What is "Demandable Capacity" in energy systems?
**Expected:** The difference between a high and low power limit (from ESA vocabulary)
**Collection:** Vocabulary
**Difficulty:** Easy

### V2. Dutch Term
**Question:** What does "Afroepbaar Vermogen" mean?
**Expected:** Dutch term for Demandable Capacity/Power - the difference between high and low power limit
**Collection:** Vocabulary
**Difficulty:** Easy

### V3. AI/ML Vocabulary
**Question:** What is Agentic RAG according to the vocabulary?
**Expected:** Definition from AAIO.ttl AI/ML concepts
**Collection:** Vocabulary
**Difficulty:** Easy

### V4. Energy Market Term
**Question:** What is the Day-Ahead Market?
**Expected:** Definition from ESA or ENTSOE vocabulary
**Collection:** Vocabulary
**Difficulty:** Easy

### V5. Regulatory Term
**Question:** What is a Metering Point according to ACER terminology?
**Expected:** Definition from ACER vocabulary
**Collection:** Vocabulary
**Difficulty:** Medium

### V6. ArchiMate Term
**Question:** What is a Business Actor in ArchiMate?
**Expected:** Definition from archimate.ttl vocabulary
**Collection:** Vocabulary
**Difficulty:** Medium

### V7. Concept Relationships
**Question:** What concepts are related to "Available Transport Capacity"?
**Expected:** Related/broader/narrower concepts from ESA vocabulary
**Collection:** Vocabulary
**Difficulty:** Hard

### V8. IEC Standard Term
**Question:** What is defined in the IEC 61970 standard?
**Expected:** Common Information Model (CIM) for energy management systems
**Collection:** Vocabulary
**Difficulty:** Medium

---

## Category 2: ADR-Specific Questions (10 questions)

### A1. Decision Lookup
**Question:** What decision was made about the domain language standard?
**Expected:** ADR-0012 - Use CIM (IEC 61970/61968/62325) as default domain language, Status: Accepted
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A2. Status Query
**Question:** What is the status of ADR-0027 about TLS security?
**Expected:** Accepted (decision date: 2025-11-14)
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A3. Decision Rationale
**Question:** Why was CIM chosen as the default domain language?
**Expected:** Semantic interoperability, reusability, compliance with energy sector standards (IEC 61970/61968/62325)
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A4. Security Decision
**Question:** What authentication and authorization standard was chosen?
**Expected:** ADR-0029 - Use OAuth 2.0 for identification, authentication and authorization
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A5. Decision Drivers
**Question:** What drove the decision to use DACI for decision-making?
**Expected:** Need for clear accountability, structured decision process (ADR-0002)
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A6. Technical Decision
**Question:** What sign convention is used for current direction?
**Expected:** ADR-0021 - Passive Sign Convention for electrical systems
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A7. Message Handling
**Question:** How should message exchange be handled in distributed systems?
**Expected:** ADR-0026 - Ensure idempotent exchange of messages for robustness
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A8. Responsibility Assignment
**Question:** Who is responsible for acquiring operational constraints in flexibility services?
**Expected:** ADR-0023 - Flexibility service provider is responsible
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A9. ADR Format
**Question:** What format is used for Architectural Decision Records?
**Expected:** ADR-0000 - Markdown ADRs using MADR format
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A10. Interface Decision
**Question:** What approach is used for Demand/Response product interfaces?
**Expected:** ADR-0025 - Unified D/R product interface for market and grid coordination via open standards
**Collection:** ArchitecturalDecision
**Difficulty:** Hard

---

## Category 3: Principle Questions (6 questions)

### P1. Principle Lookup
**Question:** What does the principle "Data is een Asset" mean?
**Expected:** Data should be captured carefully, its value utilized, and used responsibly
**Collection:** Principle
**Difficulty:** Easy

### P2. Data Design Principle
**Question:** What is the "need to know" principle for data design?
**Expected:** Principle 0011 - Data design should follow need-to-know basis
**Collection:** Principle
**Difficulty:** Medium

### P3. Data Quality
**Question:** What principle addresses data reliability?
**Expected:** "Data is betrouwbaar" (Principle 0036) - data quality assurance, fitness for purpose
**Collection:** Principle
**Difficulty:** Medium

### P4. Consistency Principle
**Question:** What does "eventual consistency by design" mean?
**Expected:** Principle 0010 - Systems should be designed to handle eventual consistency
**Collection:** Principle
**Difficulty:** Medium

### P5. Data Security
**Question:** What principle covers data access control?
**Expected:** "Data is toegankelijk" (Principle 0038) - security, access control, compliance, audit trails
**Collection:** Principle
**Difficulty:** Medium

### P6. AI Principle
**Question:** What principle guides energy-efficient AI usage?
**Expected:** Principle 0040 - Energy-efficient AI considerations
**Collection:** Principle
**Difficulty:** Medium

---

## Category 4: Policy Questions (5 questions)

### PO1. Policy Existence
**Question:** What policy document covers data governance at Alliander?
**Expected:** "Alliander Data en Informatie Governance Beleid"
**Collection:** PolicyDocument
**Difficulty:** Easy

### PO2. Data Classification
**Question:** What policies exist for classifying data products?
**Expected:** "Beleid voor het classificeren van dataproducten" and tactical classification policy
**Collection:** PolicyDocument
**Difficulty:** Medium

### PO3. Capability Framework
**Question:** What capability document addresses data integration?
**Expected:** "Capability Data-integratie en Interoperabiliteit"
**Collection:** PolicyDocument
**Difficulty:** Medium

### PO4. Master Data
**Question:** What policy covers master and reference data management?
**Expected:** "Capability Master en Referentiedata Management"
**Collection:** PolicyDocument
**Difficulty:** Medium

### PO5. Metadata Management
**Question:** Is there a policy for metadata management at Alliander?
**Expected:** Yes - "Capability Metadata Management"
**Collection:** PolicyDocument
**Difficulty:** Easy

---

## Category 5: Cross-Domain Questions (5 questions)

### X1. Principles + ADR
**Question:** How do the architecture decisions support the data governance principles?
**Expected:** CIM (ADR-0012) supports "Data is herbruikbaar" (interoperability), TLS (ADR-0027) supports "Data is toegankelijk" (security)
**Collection:** Multiple
**Difficulty:** Hard

### X2. Vocabulary + ADR
**Question:** How does the CIM standard relate to the energy vocabulary used?
**Expected:** CIM (IEC 61970/61968/62325) provides semantic basis for energy domain terms in IEC vocabularies
**Collection:** Multiple
**Difficulty:** Hard

### X3. Policy + Principles
**Question:** How does the data classification policy align with governance principles?
**Expected:** Classification supports "Data is toegankelijk" (Principle 0038) for access control
**Collection:** Multiple
**Difficulty:** Hard

### X4. Security Across Domains
**Question:** What security measures are defined across ADRs and principles?
**Expected:** TLS (ADR-0027), OAuth 2.0 (ADR-0029) + "Data is toegankelijk" principle
**Collection:** Multiple
**Difficulty:** Hard

### X5. Interoperability Theme
**Question:** How is interoperability addressed across architecture decisions?
**Expected:** CIM (ADR-0012), D/R interfaces (ADR-0025), idempotent messages (ADR-0026)
**Collection:** Multiple
**Difficulty:** Hard

---

## Category 6: Listing Queries (NEW - 3 questions)

### L1. List ADRs
**Question:** List all accepted architecture decisions related to security.
**Expected:** ADR-0027 (TLS), ADR-0029 (OAuth 2.0), possibly ADR-0026 (idempotent messages)
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### L2. List Principles
**Question:** What are all the data governance principles?
**Expected:** List including: Data is een Asset, beschikbaar, begrijpelijk, betrouwbaar, herbruikbaar, toegankelijk
**Collection:** Principle
**Difficulty:** Medium

### L3. List Vocabularies
**Question:** What vocabulary standards are available in the system?
**Expected:** IEC 61970, IEC 62325, ENTSOE-HEMRM, ACER, ArchiMate, ESA, AAIO, etc.
**Collection:** Vocabulary
**Difficulty:** Easy

---

## Category 7: Comparative Queries (NEW - 3 questions)

### C1. Compare Security Standards
**Question:** What's the difference between TLS and OAuth 2.0 in our architecture?
**Expected:** TLS (ADR-0027) secures transport layer communication; OAuth 2.0 (ADR-0029) handles authentication/authorization
**Collection:** ArchitecturalDecision
**Difficulty:** Hard

### C2. Compare Data Principles
**Question:** What's the difference between "Data is beschikbaar" and "Data is toegankelijk"?
**Expected:** Beschikbaar = availability/discoverability; Toegankelijk = access control/security
**Collection:** Principle
**Difficulty:** Medium

### C3. Compare Standards
**Question:** What's the difference between IEC 61970 and IEC 62325?
**Expected:** 61970 = Energy Management System API; 62325 = Energy Market communications
**Collection:** Vocabulary
**Difficulty:** Hard

---

## Category 8: Temporal Queries (NEW - 2 questions)

### T1. Latest Decision
**Question:** What is the most recently accepted architecture decision?
**Expected:** Should identify ADR with latest decision date (check ADR-0026 v1.0.1 from 2026-01-30)
**Collection:** ArchitecturalDecision
**Difficulty:** Hard

### T2. Decision Timeline
**Question:** When was the CIM standard decision (ADR-0012) accepted?
**Expected:** Decision date: 2025-10-23
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

---

## Category 9: Disambiguation Queries (NEW - 2 questions)

### D1. ESA Disambiguation
**Question:** What is ESA?
**Expected:** Energy System Architecture (the project/group at Alliander), NOT European Space Agency
**Collection:** Multiple
**Difficulty:** Medium

### D2. CIM Disambiguation
**Question:** What does CIM stand for in this context?
**Expected:** Common Information Model (IEC 61970/61968/62325), NOT Computer Integrated Manufacturing
**Collection:** Multiple
**Difficulty:** Medium

---

## Category 10: Negative/Edge Cases (3 questions)

### N1. Non-Existent Topic
**Question:** What is the architecture decision about using GraphQL?
**Expected:** Should indicate no such ADR exists (no hallucination)
**Collection:** None
**Difficulty:** Test

### N2. Out of Scope
**Question:** What is Alliander's policy on employee vacation days?
**Expected:** Should indicate this is not in the knowledge base
**Collection:** None
**Difficulty:** Test

### N3. Non-Existent ADR Number
**Question:** What does ADR-0050 decide?
**Expected:** Should indicate ADR-0050 does not exist (ADRs go up to ~0031)
**Collection:** None
**Difficulty:** Test

---

## Summary Table

| Category | Count | Easy | Medium | Hard | Test |
|----------|-------|------|--------|------|------|
| Vocabulary | 8 | 4 | 3 | 1 | - |
| ADR | 10 | 3 | 6 | 1 | - |
| Principles | 6 | 1 | 5 | - | - |
| Policies | 5 | 2 | 3 | - | - |
| Cross-Domain | 5 | - | - | 5 | - |
| Listing (NEW) | 3 | 1 | 2 | - | - |
| Comparative (NEW) | 3 | - | 1 | 2 | - |
| Temporal (NEW) | 2 | - | 1 | 1 | - |
| Disambiguation (NEW) | 2 | - | 2 | - | - |
| Negative/Edge | 3 | - | - | - | 3 |
| **TOTAL** | **47** | **11** | **23** | **10** | **3** |

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
| P1 | Data is een Asset | Core principle |
| P3 | Data reliability | Quality principle |
| P5 | Data access control | Security principle |
| PO1 | Data governance policy | Core policy |
| PO3 | Data integration | Capability doc |
| L2 | List principles | Listing query |
| N1 | GraphQL (non-existent) | Hallucination test |
| N3 | ADR-0050 (non-existent) | Hallucination test |

### Recommended Additions (10)
| ID | Question Topic | Why |
|----|---------------|-----|
| V6 | ArchiMate term | New vocabulary |
| A2 | TLS status | Status query |
| P4 | Eventual consistency | Technical principle |
| X1 | ADR + Principles | Cross-domain |
| X4 | Security across domains | Cross-domain |
| C1 | TLS vs OAuth | Comparative |
| C2 | Beschikbaar vs Toegankelijk | Comparative |
| T1 | Latest decision | Temporal |
| D1 | ESA disambiguation | Disambiguation |
| D2 | CIM disambiguation | Disambiguation |

### Total: 25 questions covering all categories

---

## Scoring Template

| ID | Question | Expected | Actual | Score | Notes |
|----|----------|----------|--------|-------|-------|
| V1 | Demandable Capacity | ... | | ✅/⚠️/❌/🚫 | |
| ... | ... | ... | | | |

---

## Metrics to Calculate

After running all tests:

1. **Overall Accuracy:** (✅ + 🚫) / Total
2. **Hallucination Rate:** ❌ on N1-N3 / 3
3. **Per-Category Accuracy:** Breakdown by category
4. **Difficulty Accuracy:** Easy vs Medium vs Hard
5. **Retrieval Success:** Were correct docs retrieved? (use inspector)
