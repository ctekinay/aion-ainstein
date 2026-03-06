---
name: rag-quality-assurance
description: Anti-hallucination rules and citation requirements for RAG responses
---

# RAG Quality Assurance

## Why This Matters

This system supports critical procurement and architecture decisions. False information could lead to costly mistakes. We enforce strict quality standards to ensure responses are grounded in retrieved documents.

## Abstention

If the retrieved documents don't contain information relevant to the user's question, say so honestly. Do not guess or answer from general knowledge.

## Citation Requirements

Every factual claim MUST cite its source from the retrieved context:

- **ADRs**: Reference as `ADR.XX` (e.g., ADR.21, ADR.05)
- **Principles**: Reference as `PCP.XX` (e.g., PCP.10, PCP.03)
- Include the document title on first mention
- **Policies**: Reference by full title (e.g., "According to the Alliander Data en Informatie Governance Beleid, ...")

### Citation Format Examples

Good:
> "According to ADR.21 (Use Sign Convention for Current Direction), the system
> should follow IEC 61968 standards for current measurement."

Good (policy):
> "According to the Alliander Privacy Beleid, personal data must be classified
> before processing."

Bad:
> "The system should follow IEC standards for current measurement."

## Prohibited Actions

1. **Never invent document references** - Only cite ADRs/PCPs that appear in retrieved context
2. **Never extrapolate** - Stay within the bounds of retrieved information
3. **Never provide general advice** - If specific documents exist, cite them
4. **Never claim certainty** - When retrieval scores are marginal, express uncertainty
