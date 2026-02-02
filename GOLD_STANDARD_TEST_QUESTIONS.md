# Gold Standard Test Questions for RAG Evaluation

**Instructions:** Review these 40 questions and eliminate ~15-20 to create your final test set of 20-25 questions. Consider keeping a balanced mix across categories and difficulty levels.

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
**Question:** What is Agentic RAG according to the AAIO vocabulary?
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

### V6. Technical Definition
**Question:** What is a Service Provider in the energy domain?
**Expected:** Definition from ACER or ENTSOE vocabulary
**Collection:** Vocabulary
**Difficulty:** Medium

### V7. Concept Relationships
**Question:** What concepts are related to "Available Transport Capacity"?
**Expected:** Related/broader/narrower concepts from ESA vocabulary
**Collection:** Vocabulary
**Difficulty:** Hard

### V8. Cross-vocabulary
**Question:** How is "Redispatch Products" defined in the regulatory context?
**Expected:** Definition and context from ACER vocabulary
**Collection:** Vocabulary
**Difficulty:** Medium

---

## Category 2: ADR-Specific Questions (12 questions)

### A1. Decision Lookup
**Question:** What decision was made about the domain language standard?
**Expected:** ADR-0012 - Use CIM (IEC 61970/61968/62325) as default domain language
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A2. Status Query
**Question:** What is the status of the TLS security decision (ADR-0027)?
**Expected:** Proposed
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A3. Decision Rationale
**Question:** Why was CIM chosen as the default domain language?
**Expected:** Semantic interoperability, reusability, compliance with energy sector standards
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A4. Consequences
**Question:** What are the consequences of adopting the CIM standard?
**Expected:** Complexity of CIM ontology, need to map legacy models, tooling requirements
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

### A7. Security Decision
**Question:** What TLS versions are recommended for securing data communication?
**Expected:** TLS v1.3 preferred, v1.2 acceptable (ADR-0027)
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A8. Interface Decision
**Question:** What approach is proposed for Demand/Response product interfaces?
**Expected:** ADR-0025 - Unified D/R product interface for market and grid coordination, multivendor interoperability
**Collection:** ArchitecturalDecision
**Difficulty:** Hard

### A9. Message Handling
**Question:** How should message exchange be handled in distributed systems?
**Expected:** ADR-0026 - Ensure idempotent exchange of messages for robustness
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A10. Responsibility Assignment
**Question:** Who is responsible for acquiring operational constraints in flexibility services?
**Expected:** ADR-0023 - Flexibility service provider is responsible
**Collection:** ArchitecturalDecision
**Difficulty:** Medium

### A11. ADR Format
**Question:** What format is used for Architectural Decision Records?
**Expected:** ADR-0000 - Markdown ADRs using MADR 4.0.0 format
**Collection:** ArchitecturalDecision
**Difficulty:** Easy

### A12. Standards Priority
**Question:** How are origins of standardizations prioritized?
**Expected:** ADR-0010 content about prioritization approach
**Collection:** ArchitecturalDecision
**Difficulty:** Hard

---

## Category 3: Principle Questions (6 questions)

### P1. Principle Lookup
**Question:** What does the principle "Data is een Asset" mean?
**Expected:** Data should be captured carefully, its value utilized, and used responsibly
**Collection:** Principle
**Difficulty:** Easy

### P2. Data Availability
**Question:** What does the "Data is beschikbaar" principle state?
**Expected:** Data should be available, discoverable, and accessible
**Collection:** Principle
**Difficulty:** Easy

### P3. Data Quality
**Question:** What principle addresses data reliability?
**Expected:** "Data is betrouwbaar" - data quality assurance, fitness for purpose
**Collection:** Principle
**Difficulty:** Medium

### P4. Data Reusability
**Question:** How should data be standardized according to the governance principles?
**Expected:** "Data is herbruikbaar" - standardization, interoperability
**Collection:** Principle
**Difficulty:** Medium

### P5. Data Security
**Question:** What principle covers data access control?
**Expected:** "Data is toegankelijk" - security, access control, compliance, audit trails
**Collection:** Principle
**Difficulty:** Medium

### P6. Principle Application
**Question:** How do the data governance principles ensure data is understandable?
**Expected:** "Data is begrijpelijk" - consistent definitions, metadata, information models
**Collection:** Principle
**Difficulty:** Medium

---

## Category 4: Policy Questions (6 questions)

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

### PO6. Quality Management
**Question:** What document addresses data quality management?
**Expected:** "Capability Data- en Informatie Kwaliteit Management"
**Collection:** PolicyDocument
**Difficulty:** Medium

---

## Category 5: Cross-Domain Questions (5 questions)

### X1. Principles + ADR
**Question:** How do the ADRs support the data governance principles?
**Expected:** Should reference how CIM (ADR-0012) supports "Data is herbruikbaar" (interoperability)
**Collection:** Multiple
**Difficulty:** Hard

### X2. Vocabulary + ADR
**Question:** How does the CIM standard relate to the energy vocabulary used?
**Expected:** CIM provides semantic basis for energy domain terms
**Collection:** Multiple
**Difficulty:** Hard

### X3. Policy + Principles
**Question:** How does the data classification policy align with governance principles?
**Expected:** Classification supports "Data is toegankelijk" (access control)
**Collection:** Multiple
**Difficulty:** Hard

### X4. Security Across Domains
**Question:** What security measures are defined across ADRs and policies?
**Expected:** TLS (ADR-0027) + access control from "Data is toegankelijk" + governance policies
**Collection:** Multiple
**Difficulty:** Hard

### X5. Interoperability Theme
**Question:** How is interoperability addressed across architecture decisions and policies?
**Expected:** CIM (ADR-0012), D/R interfaces (ADR-0025), Data Integration capability
**Collection:** Multiple
**Difficulty:** Hard

---

## Category 6: Negative/Edge Cases (3 questions)

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

### N3. Partial Information
**Question:** What decisions have been deprecated or superseded?
**Expected:** Should honestly state if none exist or list any that do
**Collection:** ArchitecturalDecision
**Difficulty:** Test

---

## Summary Table

| Category | Count | Easy | Medium | Hard | Test |
|----------|-------|------|--------|------|------|
| Vocabulary | 8 | 4 | 3 | 1 | - |
| ADR | 12 | 3 | 7 | 2 | - |
| Principles | 6 | 2 | 4 | - | - |
| Policies | 6 | 2 | 4 | - | - |
| Cross-Domain | 5 | - | - | 5 | - |
| Negative/Edge | 3 | - | - | - | 3 |
| **TOTAL** | **40** | **11** | **18** | **8** | **3** |

---

## Recommended Final Selection (20-25)

To get a balanced test set, consider keeping:

**Must Keep (Core Coverage):**
- V1, V3, V4 (Vocabulary basics)
- A1, A3, A4, A7, A9 (ADR coverage)
- P1, P3, P5 (Principles)
- PO1, PO3 (Policies)
- N1 (Negative test)

**Consider Adding:**
- V7 (Hard vocabulary - relationships)
- A8 (Complex ADR)
- X1 or X4 (Cross-domain)
- N2 or N3 (More edge cases)

**OK to Remove (Redundant/Similar):**
- V2 (similar to V1)
- V5, V6, V8 (if vocabulary coverage sufficient)
- A2, A5, A6, A10, A11 (if ADR coverage sufficient)
- P2, P4, P6 (if principle coverage sufficient)
- PO2, PO4, PO5, PO6 (if policy coverage sufficient)
- X2, X3, X5 (keep 1-2 cross-domain)

---

## Next Steps

1. Review and eliminate ~15-20 questions
2. Run baseline tests with remaining 20-25
3. Score each response manually (✅/⚠️/❌/🚫)
4. Calculate baseline accuracy per category
5. Use results to identify weak areas (retrieval vs generation)
