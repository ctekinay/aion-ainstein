# Token Budget Strategy

Heuristics for how Claude allocates attention when processing `architecture_notes.json`
and determining model scope.

---

## Repo Size Tiers

| Tier | File count | Components | Strategy |
|---|---|---|---|
| Small | < 50 files | 1–3 services | Read everything. Single LLM pass. Full model in one step. |
| Medium | 50–500 files | 4–15 services | Read everything. Single LLM pass. May need 2 view generation passes. |
| Large | 500+ files | 15+ services | Read summary first. Ask user to scope to specific modules. Process in batches — generate model for subset, then extend with `patch_model.py`. |

---

## Budget Allocation by Phase

| Phase | Small repo | Medium repo | Large repo |
|---|---|---|---|
| Read architecture_notes.json | ~3,000 tokens | ~8,000–15,000 tokens | ~20,000–40,000 tokens (scoped) |
| Read reference docs | ~4,000 tokens (fixed) | ~4,000 tokens (fixed) | ~4,000 tokens (fixed) |
| LLM classification reasoning | ~2,000 tokens | ~5,000 tokens | ~8,000 tokens |
| Output archimate_model.json | ~1,000 tokens | ~3,000–8,000 tokens | ~5,000–15,000 tokens |
| View generation reasoning | ~500 tokens | ~1,000 tokens | ~2,000 tokens |
| **Total** | **~10,000 tokens** | **~20,000–30,000 tokens** | **~40,000–70,000 tokens** |

---

## Scoping Strategy for Large Repos

When architecture_notes.json exceeds ~30 KB (est. ~7,500 tokens), ask the user:

> "This repository has N components and M infrastructure services. To produce
> a focused, high-quality model, I recommend scoping to a subset first.
>
> Options:
> 1. **Full model** — all components (larger model, may be less detailed)
> 2. **Core services only** — top N components by connectivity (most relationships)
> 3. **Specific domain** — select which services to include
> 4. **Layer focus** — Application layer only / Technology layer only / Full stack
>
> Which approach would you prefer?"

### Batch Processing for Full Large Models

If the user wants a full model of a large repo:

1. **Pass 1:** Generate the model for components 1–10 with all their infrastructure.
   Output via `json_to_archimate.py`.
2. **Pass 2–N:** For each remaining batch of components, generate a patch JSON and
   apply via `patch_model.py`.
3. **Final:** Generate views on the complete model.

This keeps each LLM pass under ~30K tokens while building the complete model incrementally.

---

## Adaptive Depth Control

The depth of ArchiMate modeling should match the information available:

| Available information | Modeling depth |
|---|---|
| Only docker-compose + README | Basic: ApplicationComponents + SystemSoftware + Serving relationships |
| docker-compose + code structure | Standard: above + DataObjects, ApplicationServices, Access relationships |
| docker-compose + code + API specs | Rich: above + ApplicationInterfaces, detailed endpoints in documentation |
| All of the above + Terraform/Helm | Full: above + Nodes, CommunicationNetworks, deployment topology |
| Above + ADRs/requirements docs | Complete: above + Motivation layer (Goals, Principles, Requirements) |

**Rule:** Never hallucinate architectural detail that isn't supported by evidence in
the extracted data. If there's no API spec, don't invent endpoints. If there's no
Terraform, don't invent cloud infrastructure.

---

## View Generation Budget

| Condition | Views to generate | Token cost |
|---|---|---|
| ≤ 10 elements | 1 Layered View | ~500 tokens |
| 10–40 elements | Application View + Technology View | ~1,000 tokens |
| 40–80 elements | Application View + Technology View + per-cluster views | ~2,000 tokens |
| 80+ elements | Application View + Technology View (warn: views may be crowded) | ~1,500 tokens |

Always offer to generate additional focused views after the initial model is delivered.
