# Fake shared reference

This file exists to verify the fixture plugin's shared-references/
directory is correctly resolved through `Plugin.shared_refs_dir` +
the `SkillRegistry._merge_shared_references` path. Skills routing to
the `fake-group` group via `shared_references: fake-group` would
receive this content merged into their reference set.

The fixture's two skills don't use a group, so this file is currently
unconsumed — it's present as scaffold for future tests that exercise
the shared-refs path.
