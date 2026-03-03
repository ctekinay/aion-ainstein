#!/usr/bin/env python3
"""Layer 1 test: Registry + Loader data model verification."""

from src.aion.skills.registry import get_skill_registry

r = get_skill_registry()

# Groups loaded?
groups = r.list_groups()
print(f"Groups: {len(groups)}")
for g in groups:
    print(f"  {g.name}: {g.skills}, enabled={g.enabled}")

print()

# All skills loaded with correct fields?
for e in r.list_skills():
    print(f"  {e.name}: group={repr(e.group)}, type={e.type}, load_order={e.load_order}, enabled={e.enabled}")

# References skill loads without SKILL.md?
content = r.get_skill_content(active_tags=["archimate"])
print(f"\nInjected content length: {len(content)} chars")

has_generator = "ArchiMate" in content
has_mapping = "Input concept" in content
print(f"Contains generator rules: {has_generator}")
print(f"Contains concept-mapping: {has_mapping}")

# Verify load order: generator content appears before references content
if has_generator and has_mapping:
    gen_pos = content.index("ArchiMate")
    map_pos = content.index("Input concept")
    print(f"Load order correct (generator before references): {gen_pos < map_pos}")
    print(f"  Generator position: {gen_pos}, References position: {map_pos}")
