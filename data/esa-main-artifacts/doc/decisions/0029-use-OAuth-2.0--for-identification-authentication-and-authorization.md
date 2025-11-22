---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 29
title: Use OAuth 2.0 (with OpenID Connect where needed) for Identification, Authentication and Authorization
status: proposed
date: YYYY-MM-DD when the decision was last updated

driver: Robert-Jan Peters <robert-jan.peters@alliander.com>
#approvers: list everyone with the final say in this ADR.
contributors: Edi Recica <edi.recica@alliander.com>, René Kleizen <rene.kleizen@alliander.com>
#informed: list everyone who need to be aware of the decision once made. 

# These are optional elements. Feel free to remove any of them.
# additional decision-makers: {list everyone involved in the decision}
---

<!-- markdownlint-disable-next-line MD025 -->

# Use OAuth 2.0 (with OpenID Connect where needed) for Identification, Authentication, and Authorization

## Context and Problem Statement

In the flexibility market, actors such as aggregators, Distribution System Operators (DSOs), Balance Responsible
Parties (BRPs), and Flexibility Service Providers (FSPs) require access to operational constraints and related
information to plan, forecast, and activate flexibility services. This access involves sensitive operational and
personal data governed by market rules, GDPR, and grid codes. However, there is currently no standardized mechanism to
ensure secure, auditable, and role-based access to such data across platforms and market participants.

As a result, implementations often differ in how they handle identification, authentication, and authorization—leading
to inconsistent enforcement of access rules, limited auditability, and increased risk of unauthorized or non-compliant data
access.

- Identification – recognizing and registering organizations and actors as legitimate market participants.
- Authentication – validating the digital identity of each participant or system requesting access.
- Authorization – granting access exclusively to data and operations permitted by the participant’s contractual, market,
  or regulatory role.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Enforce least-privilege access, delegated authorization, and fine-grained permission control (roles, scopes, claims)
  to mitigate risk and enhance accountability.
* Enable federated identity support across multiple market participants and systems, allowing each organization to
  maintain its own identity provider while participating in a shared trust framework.
* Enable a consistent authentication and authorization model across all client types — human, machine, and system —
  reducing complexity in implementation and governance.
* Enable both human users (e.g., operator portals) and machine clients (e.g., API-to-API or service-to-service) to
  streamline operations and enable automated flexibility services.
* Enable token revocation, credential rotation, and adaptive authorization to quickly respond to evolving security
  threats or operational incidents.
* Comply with EU cybersecurity and energy sector interoperability frameworks (e.g., IEC 62325, NIS2), ensuring readiness
  for regulatory audits and certification.
* Provide traceability and auditability of access and data usage, supporting oversight, compliance, and forensic
  investigation capabilities.

## Considered Options

The following options are considered:

1. SAML 2.0 Federation Only<p>Provides federated identity and Single Sign-On (SSO) across organizations using XML
   assertions; mature for enterprises but limited for APIs.
2. Custom API Key System<p>Issues static keys for API access; simple and easy to implement but lacks delegation,
   revocation, and fine-grained authorization.
3. Auth 2.0 + OIDC<p>Uses standardized token-based authorization and identity federation; supports human and machine
   actors with scopes and roles; requires IdP setup.
4. Mutual TLS Authentication Only<p>Authenticates systems via X.509 certificates during TLS handshake; highly secure but
   unsuitable for user-level or delegated access.

## Decision Outcome

The outcome is **Option 3** to use **OAuth 2.0** as the core **authorization and delegated access framework**, and *
*OpenID Connect (OIDC)** on top of it for **identification and authentication**.

### Consequences

### Positive

- Standards-based and interoperable.
- Enables SSO, delegated authorization, and fine-grained access.
- Centralized security and policy enforcement.
- Strong ecosystem support (libraries, IdPs).
- Supports human and machine actors consistently.

### Negative / Trade-offs

- Adds operational complexity (IdP management, key rotation).
- Increases dependency on Authorization Server availability.
- Migration of legacy systems may require refactoring.
- Misconfiguration can introduce vulnerabilities.

## Pros and Cons of the Options

1. SAML 2.0 + Custom ACL
    - Enterprise SSO support
    - Poor fit for APIs and mobile apps

2. Custom Token System (API keys, sessions)
    - Simple initially
    - Reimplements solved problems, poor interoperability

3. OAuth 2.0 without OIDC
    - Simpler stack
    - OAuth2 alone is not an authentication protocol

4. Mutual TLS (mTLS) Only
    - Strong machine authentication
    - Poor usability for user-facing flows
    - Adds operational complexity in operation (key-rotation, retention-period)

## More Information

### Architecture Implications

- Introduce a central **Authorization Server / IdP** supporting OIDC.
- APIs act as **Resource Servers** enforcing scopes and claims.
- Classify clients as **confidential** or **public**.
- Centralize scope-to-role-to-permission mapping.
- Implement **key management** and **JWKS rotation** processes.
- Integrate **monitoring and audit logging**.

### Security Considerations

- **TLS required** for all communication.
- **PKCE** mandatory for public clients.
- **Short-lived access tokens** (5–15 minutes).
- **Refresh token rotation** enabled.
- **Revocation endpoint** implemented and enforced.
- **JWKS** used for key management and rotation.
- **MFA** supported at IdP level.
- **Secure token storage:** no refresh tokens in localStorage; use secure cookies or mobile secure stores.
- **CSRF and nonce validation** required for front-end flows.
- **Rate-limiting and anomaly detection** at token endpoints.

### Operational Requirements

- Highly available Authorization Server (replication/failover).
- Secure key storage (HSM or equivalent).
- Key rotation and secure JWKS publication.
- Incident response plan for token/secret compromise.
- SLAs and monitoring for IdP uptime.

## References

- [RFC 6749: OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc6749)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 8693: OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693)
- [OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
