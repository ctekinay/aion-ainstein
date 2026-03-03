---
# Configuration for the Jekyll template "Just the Docs"
#@prefix dct: <http://purl.org/dc/terms>
nav_order: ADR.27D
dct:
  identifier: urn:uuid:b4c5d6e7-f8a9-4b0c-1d2e-3f4a5b6c7d8e
  title: Use TLS to secure data communication
---

# Decision Approval Record List

## 1. Creation and ESA Approval of ADR.27

| Name                  | Value                                                |
|-----------------------|------------------------------------------------------|
| Version of ADR        | v1.0.0 (2025-11-14)                                  |
| Decision              | Accepted                                             |
| Decision date         | 2025-11-14                                           |
| Driver (Decision owner)        | System Operations - Energy System Architecture Group |
| Remarks               |                                                      |


**Approvers**

| Name | Email | Role | Comments |
|------|-------|------|----------|
| Robert-Jan Peters | robert-jan.peters@alliander.com | Energy System Architect | |
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect | |

**Additional Notes**
The acceptance of this principle included the consideration about post-quantum challenges
on braking any encryption. However, as the alternatives does not provide the same level
of protection locally (on-site) and between two locations, this is the best possible for now.
New developments (e.g. application layer protection in Signal Messenger) to be investigated
till mature application into control systems.
