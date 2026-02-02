---
# Configuration for the Jekyll template "Just the Docs"
#@prefix dct: <http://purl.org/dc/terms>
nav_order: ADR.12D
dct:
  identifier: urn:uuid:f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f8a9b0c
  title: Use CIM as default domain language
---

# Decision Approval Record List

## Creation and ESA Approval of ADR.12

| Name                    | Value                                                |
|-------------------------|------------------------------------------------------|
| Version of ADR          | v1.0.0 (2025-05-25)                                  |
| Decision                | Accepted                                             |
| Decision date           | 2025-10-23                                           |
| Driver (Decision owner) | System Operations - Energy System Architecture Group |
| Remarks                 |                                                      |

**Approvers**

| Name                  | Email                               | Role                    | Comments |
|-----------------------|-------------------------------------|-------------------------|----------|
| Robert-Jan Peters     | robert-jan.peters@alliander.com     | Energy System Architect |          |
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect |          |

**Additional Notes**
As currently the different information domains are not sufficiently defined at Alliander, this ADR
respects other domains with their specific information models and corresponding semantics, like building, finance, etc.
The essence is, IEC CIM is the leading semantic standard for our key operational processes and enables connections
to other domains.
