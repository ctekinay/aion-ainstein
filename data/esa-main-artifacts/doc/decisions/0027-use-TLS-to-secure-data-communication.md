---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 27
title: Use TLS to Secure Data Communication
status: proposed
date: YYYY-MM-DD when the decision was last updated

driver: Robert-Jan.Peters <robert-jan.peters@alliander.com>,
#approvers: list everyone with the final say in this ADR.
contributors: Edi Recica <edi.recica@alliander.com>, René Kleizen <rene.kleizen@alliander.com>
#informed: list every one who need to be aware of the decision once made.

# These are optional elements. Feel free to remove any of them.
# additional decision-makers: {list everyone involved in the decision}
---

<!-- markdownlint-disable-next-line MD025 -->

# Use TLS to Secure Data Communication

## Context and Problem Statement

The System Operator's infrastructure consists of a complex network of interconnected systems that exchange sensitive
data across untrusted networks (LAN/WAN/Internet). This includes customer personal information, grid operational data,
system configuration parameters, and operating constraints that flow between internal services, field devices, and
third-party service providers.

The current security landscape reveals significant gaps in our communication infrastructure. Several channels remain
unencrypted, while others rely on outdated cryptographic protocols, creating potential vulnerabilities in our data
transmission. This situation is particularly concerning given that our systems operate across various network boundaries
including local area networks, wide area networks, and the public Internet.

Both regulatory frameworks (such as GDPR and IEC standards) and our contractual obligations mandate robust security
measures for data in transit. These requirements specifically emphasize three critical aspects: confidentiality to
prevent unauthorized access, integrity to ensure data hasn't been tampered with, and non-repudiation to guarantee the
authenticity of communications between parties.

These circumstances require the implementation of a standardized security approach that can effectively protect our
diverse data flows while maintaining system interoperability and operational efficiency.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Ensure compliance with data protection and cybersecurity standards to safeguard system operations and stakeholder
  trust.
* Maintain confidentiality and integrity of data in transit to prevent unauthorized access or tampering during
  communication between systems.
* Enable interoperability with third-party systems to support seamless integration and data exchange across
  organizational and vendor boundaries.
* Promote operational simplicity through efficient certificate lifecycle management and minimized administrative
  overhead.
* Ensure performance and scalability to handle increasing data volumes and system growth without degradation in
  responsiveness or reliability.

## Considered Options

1. Use TLS (v1.3 preferred, v1.2 fallback) for all communications
2. Use IPsec or VPN tunnels for network-level encryption
3. Use application-layer encryption (payload-level)

## Decision Outcome

The outcome is **Option 1** to use TLS (v1.3 preferred, v1.2 fallback) for all data communications.

TLS provides the best balance between security, interoperability, and operational maintainability.  
It allows standardized configuration, integrates well with modern tooling, and supports both server and client
authentication. Other options (IPsec, application-layer encryption) either add complexity or fail to meet identity and
compliance requirements.

### Consequences

#### Positive Consequences

- Provides confidentiality, integrity, and authentication via a well-established standard.
- Simplifies compliance with regulatory and industry security requirements.
- Centralizes certificate management and operational processes.
- Reduces risk of data interception or tampering.

#### Negative Consequences

- Requires ongoing certificate issuance and rotation management.
- Potential interoperability issues with legacy systems.
- Minimal performance overhead due to cryptographic operations.

## Pros and Cons of the Options

### 1. Use TLS (v1.3 preferred, v1.2 fallback)

**Pros:**

- Widely supported and standardized (RFC 8446)
- Provides strong confidentiality and integrity
- Enables automated certificate management (ACME, Vault)

**Cons:**

- Overhead for certificate rotation and monitoring
- Some legacy endpoints may not support TLS 1.2+

### 2. Use IPsec / VPN Tunnels

**Pros:**

- Transparent to applications
- Strong encryption at the network layer

**Cons:**

- No service-level identity verification
- Complex network configuration and scaling issues
- Limited visibility for application-layer security

### 3. Use Application-layer Encryption

**Pros:**

- End-to-end protection even through intermediaries
- Can enforce fine-grained access controls

**Cons:**

- Complex to implement and maintain
- Increases application coupling and key management overhead

## Implementation Details

- Default to **TLS 1.3**, fallback to **TLS 1.2** when strictly required.
- Disable deprecated protocols (SSLv2/3, TLSv1.0/1.1) and weak ciphers.
- X509 based authentication by ECDSA, RSA(RSA-PSS), or EdDSA.
- AEAD ciphers, like AES-256-GCM and ChaCha20-Poly1305, provide both confidentiality and integrity for encrypted data,
  ensuring that the message cannot be tampered with without detection.
- Certificates issued by internal PKI or trusted public CA.
- Automate certificate issuance and renewal (ACME / Vault integrations).
- Certificates valid for ≤ 90 days; automatic renewal enforced.
- TLS configuration testing in CI/CD (testssl.sh - https://testssl.sh/, SSL Labs
  scans - https://www.ssllabs.com/ssltest/).

## More Information

- [Alliander Informatie Security Management Systeem](https://intranet.alliander.com/alliander-1-isms)
- [CISO security maatregelen](https://intranet.alliander.com/ciso-security-maatregelen)

- [Dutch Security Guidelines for Transportation Layer Security 2025-05](https://www.ncsc.nl/binaries/ncsc/documenten/publicaties/2025/juni/01/ict-beveiligingsrichtlijnen-voor-transport-layer-security-2025-05/Publication_TLS-Security+guidelines-2025-05_ENG.pdf)
- [RFC 8446 — TLS 1.3 Specification](https://datatracker.ietf.org/doc/html/rfc8446)
- [OWASP Transport Layer Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html)
- [NIST SP 800-52 Rev. 2 — Guidelines for the Selection and Use of TLS](https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final)
- [IEC 62351-3 — Secure Communication in Power System Management](https://webstore.iec.ch/publication/26773)
