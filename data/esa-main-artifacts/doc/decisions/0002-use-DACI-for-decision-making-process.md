---
parent: Decisions
nav_order: 2

# These are optional elements. Feel free to remove any of them.
status: "accepted"
date: "2025-07-17"
approvers: "Energy System Architecture: Robert-Jan Peters, Laurent van Groningen"
consulted: "no"
informed: "BBN architecture, ART-SO solution architecture"
---
# Use DACI for Decision-Making Process?

## Context and Problem Statement

In modern software development, systems are becoming increasingly complex, distributed, and interdependent. As a result,
architectural decisions—such as choosing a technology stack, defining system boundaries, or selecting integration
patterns—have a significant and lasting impact on the system's quality attributes, maintainability, and scalability. To
manage this complexity and ensure transparency, many teams adopt Architectural Decision Records (ADRs) as a lightweight,
structured approach to documenting key architectural decisions.

ADRs capture the rationale behind decisions, the alternatives considered, and the consequences of each
choice. This documentation becomes a valuable artifact for onboarding new team members, revisiting past decisions, and
ensuring alignment across stakeholders. However, without a clear and consistent decision-making process, ADRs can become
inconsistent, incomplete, or even misleading.

Without a structured ADR process, decisions may lack proper documentation, stakeholder alignment, and long-term
visibility—leading to confusion, technical debt, and reduced system agility.

## Decision Drivers

* Clarity of roles -- who is involved in making decisions and who is impacted.
* Simple -- must be easy to explain and understand.

## Considered Options

* DACI
* RACI
* RAPID

# Decision Outcome

We will adopt the [DACI](https://www.productplan.com/glossary/daci/)
framework for our decision-making process. DACI stands for:

- **D**river: Person driving the project and responsible for the
  decision-making process. This person should understand the project
  and facilitate communication among stakeholders.

- **A**pprovers: Individual(s) with the final say. Typically,
  individuals in this role possess the authority to make decisions.

- **C**ontributors: Those providing valuable input to the decision.
  Contributors can be anyone with relevant information or expertise.

- **I**nformed: People who need to be aware of the decision once made.
  These could be team members impacted by the decision or other
  stakeholders.

At a minimum, we will apply DACI to:

1. Design Documents: To decide on the best design approach.
2. Any/Architectural Decision Records (ADRs): To drive decision-making
   for system-wide changes.

## Pros and Cons of the Options

### RACI

[RACI](https://en.wikipedia.org/wiki/Responsibility_assignment_matrix)
stands for Responsible, Accountable, Consulted, and Informed. While it
provides a similar structure to DACI, the difference in terms can sometimes
lead to ambiguity, such as distinguishing between "Responsible" and
"Accountable".

### RAPID

[RAPID](https://www.bridgespan.org/insights/rapid-decision-making)
stands for Recommend, Agree, Perform, Input, and Decide. This model
emphasizes decision execution but can be overly complex, especially
for smaller teams and less hierarchical organizations.

## Consequences

Adopting DACI is expected to enhance our decision-making process,
promoting clarity and efficiency. It requires a learning period and
may require adjustments in our workflows. Ultimately, it's
expected to cultivate a more transparent and efficient environment.

## More Information

Inspired by a blog on [Dev Details](https://blog.devdetails.com/)

### Suggestions for Adoption

To migrate to DACI, we can:

1. **Present**: Conduct sessions to familiarize the team with DACI.
2. **Implement Incrementally**: Begin with one project and gradually
   expand its usage.
3. **Regular Reviews**: Schedule reviews to assess DACI effectiveness
   and make adjustments.

