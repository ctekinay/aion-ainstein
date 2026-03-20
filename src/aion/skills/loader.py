"""Skill loader for parsing and loading Agent Skills.

This module implements loading of skills following the agentskills.io
open standard format. Skills are folders containing a SKILL.md file
with YAML frontmatter and markdown instructions.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default skills directory relative to project root
DEFAULT_SKILLS_DIR = Path(__file__).parent.parent.parent.parent / "skills"


@dataclass
class Skill:
    """Represents a loaded skill."""

    name: str
    description: str
    content: str  # The markdown body (instructions)
    path: Path
    references: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)

    def get_injectable_content(self) -> str:
        """Get the skill content formatted for prompt injection.

        Includes markdown reference files (strings) from skill.references.
        YAML-parsed references (dicts from thresholds.yaml etc.) are excluded
        via isinstance check — they're config, not prompt content.
        """
        parts = [f"## Skill: {self.name}\n\n{self.content}"]
        for ref_name, ref_content in sorted(self.references.items()):
            if isinstance(ref_content, str):
                parts.append(f"### {ref_name}\n\n{ref_content}")
        return "\n\n---\n\n".join(parts)


class SkillLoader:
    """Loads and parses skills from the skills directory."""

    def __init__(self, skills_dir: Path | None = None):
        """Initialize the skill loader.

        Args:
            skills_dir: Path to skills directory. Defaults to project's skills/ folder.
        """
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self._cache: dict[str, Skill] = {}

    def load_skill(
        self, skill_name: str, skill_type: str = "skill"
    ) -> Skill | None:
        """Load a skill by name.

        Args:
            skill_name: Name of the skill (folder name)
            skill_type: "skill" (default, reads SKILL.md) or "references"
                (globs references/*.md, no SKILL.md required)

        Returns:
            Loaded Skill object or None if not found
        """
        cache_key = f"{skill_name}:{skill_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        skill_path = self.skills_dir / skill_name

        # Reference-only skills: concatenate all .md files from references/
        if skill_type == "references":
            return self._load_references_skill(skill_name, skill_path)

        skill_md_path = skill_path / "SKILL.md"

        if not skill_md_path.exists():
            logger.warning(f"Skill not found: {skill_name} (looked in {skill_md_path})")
            return None

        try:
            skill = self._parse_skill_file(skill_md_path)
            if skill:
                skill.references = self._load_references(skill_path)
                skill.thresholds = self._load_thresholds(skill_path)
                self._cache[cache_key] = skill
            return skill
        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return None

    def _load_references_skill(
        self, skill_name: str, skill_path: Path
    ) -> Skill | None:
        """Build a Skill from a references/ directory (no SKILL.md needed)."""
        refs_dir = skill_path / "references"
        if not refs_dir.exists():
            logger.warning(
                f"References dir not found for skill: {skill_name} "
                f"(looked in {refs_dir})"
            )
            return None

        parts = []
        references = {}
        for f in sorted(refs_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
                parts.append(f"## {f.stem}\n\n{text}")
                references[f.stem] = text
            except Exception as e:
                logger.warning(f"Failed to read reference {f}: {e}")

        if not parts:
            logger.warning(f"No .md files found in {refs_dir}")
            return None

        content = "\n\n---\n\n".join(parts)
        skill = Skill(
            name=skill_name,
            description=f"Reference library ({len(parts)} files)",
            content=content,
            path=skill_path,
            references=references,
        )
        self._cache[f"{skill_name}:references"] = skill
        logger.debug(
            f"Loaded references skill: {skill_name} ({len(parts)} files)"
        )
        return skill

    def _parse_skill_file(self, skill_md_path: Path) -> Skill | None:
        """Parse a SKILL.md file.

        Args:
            skill_md_path: Path to SKILL.md file

        Returns:
            Parsed Skill object or None on error
        """
        content = skill_md_path.read_text(encoding="utf-8")

        frontmatter_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n(.*)$",
            content,
            re.DOTALL
        )

        if not frontmatter_match:
            logger.error(f"Invalid SKILL.md format (no frontmatter): {skill_md_path}")
            return None

        frontmatter_str = frontmatter_match.group(1)
        markdown_body = frontmatter_match.group(2).strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML frontmatter in {skill_md_path}: {e}")
            return None

        name = frontmatter.get("name")
        description = frontmatter.get("description")

        if not name:
            logger.error(f"Missing 'name' in frontmatter: {skill_md_path}")
            return None

        if not description:
            logger.warning(f"Missing 'description' in frontmatter: {skill_md_path}")
            description = ""

        return Skill(
            name=name,
            description=description,
            content=markdown_body,
            path=skill_md_path.parent,
        )

    def _load_references(self, skill_path: Path) -> dict[str, Any]:
        """Load all reference files from a skill's references/ directory."""
        references = {}
        refs_dir = skill_path / "references"

        if not refs_dir.exists():
            return references

        for ref_file in refs_dir.iterdir():
            if ref_file.is_file():
                try:
                    if ref_file.suffix in (".yaml", ".yml"):
                        references[ref_file.stem] = yaml.safe_load(
                            ref_file.read_text(encoding="utf-8")
                        )
                    else:
                        references[ref_file.stem] = ref_file.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to load reference {ref_file}: {e}")

        return references

    def _load_thresholds(self, skill_path: Path) -> dict[str, Any]:
        """Load thresholds from a skill's references/thresholds.yaml."""
        thresholds_path = skill_path / "references" / "thresholds.yaml"

        if not thresholds_path.exists():
            return {}

        try:
            return yaml.safe_load(thresholds_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning(f"Failed to load thresholds from {thresholds_path}: {e}")
            return {}

    def get_skill_content(self, skill_name: str) -> str:
        """Get the injectable content for a skill."""
        skill = self.load_skill(skill_name)
        if skill:
            return skill.get_injectable_content()
        return ""

    def get_thresholds(self, skill_name: str) -> dict[str, Any]:
        """Get thresholds configuration for a skill."""
        skill = self.load_skill(skill_name)
        if skill:
            return skill.thresholds
        return {}

    def get_abstention_thresholds(self, skill_name: str) -> float:
        """Get the distance threshold for abstention.

        Args:
            skill_name: Name of the skill

        Returns:
            Distance threshold (default 0.5)
        """
        thresholds = self.get_thresholds(skill_name)
        abstention = thresholds.get("abstention", {})
        return abstention.get("distance_threshold", 0.5)

    def get_retrieval_limits(self, skill_name: str) -> dict[str, int]:
        """Get retrieval limits for a skill."""
        thresholds = self.get_thresholds(skill_name)
        return thresholds.get("retrieval_limits", {
            "adr": 8,
            "principle": 6,
            "policy": 4,
            "vocabulary": 4,
        })

    def get_truncation(self, skill_name: str) -> dict[str, int]:
        """Get content truncation limits for a skill."""
        thresholds = self.get_thresholds(skill_name)
        return thresholds.get("truncation", {
            "content_max_chars": 800,
            "tool_content_chars": 500,
            "tool_summary_chars": 300,
            "consequences_max_chars": 4000,
            "direct_doc_max_chars": 12000,
        })

    def get_tree_config(self, skill_name: str) -> dict[str, int]:
        """Get RAG agent configuration (recursion limit, etc.)."""
        thresholds = self.get_thresholds(skill_name)
        return thresholds.get("tree", {
            "recursion_limit": 6,
        })

    def clear_cache(self):
        """Clear the skill cache."""
        self._cache.clear()
