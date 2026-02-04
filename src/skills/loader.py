"""Skill loader for parsing and loading Agent Skills.

This module implements loading of skills following the agentskills.io
open standard format. Skills are folders containing a SKILL.md file
with YAML frontmatter and markdown instructions.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Default skills directory relative to project root
DEFAULT_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


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
        """Get the skill content formatted for prompt injection."""
        return f"## Skill: {self.name}\n\n{self.content}"


class SkillLoader:
    """Loads and parses skills from the skills directory."""

    def __init__(self, skills_dir: Optional[Path] = None):
        """Initialize the skill loader.

        Args:
            skills_dir: Path to skills directory. Defaults to project's skills/ folder.
        """
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self._cache: dict[str, Skill] = {}

    def load_skill(self, skill_name: str) -> Optional[Skill]:
        """Load a skill by name.

        Args:
            skill_name: Name of the skill (folder name)

        Returns:
            Loaded Skill object or None if not found
        """
        # Check cache first
        if skill_name in self._cache:
            return self._cache[skill_name]

        skill_path = self.skills_dir / skill_name
        skill_md_path = skill_path / "SKILL.md"

        if not skill_md_path.exists():
            logger.warning(f"Skill not found: {skill_name} (looked in {skill_md_path})")
            return None

        try:
            skill = self._parse_skill_file(skill_md_path)
            if skill:
                # Load references if they exist
                skill.references = self._load_references(skill_path)
                skill.thresholds = self._load_thresholds(skill_path)
                self._cache[skill_name] = skill
            return skill
        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return None

    def _parse_skill_file(self, skill_md_path: Path) -> Optional[Skill]:
        """Parse a SKILL.md file.

        Args:
            skill_md_path: Path to SKILL.md file

        Returns:
            Parsed Skill object or None on error
        """
        content = skill_md_path.read_text(encoding="utf-8")

        # Parse YAML frontmatter
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

        # Validate required fields
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
        """Load all reference files from a skill's references/ directory.

        Args:
            skill_path: Path to the skill directory

        Returns:
            Dictionary mapping filename to parsed content
        """
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
                    elif ref_file.suffix == ".md":
                        references[ref_file.stem] = ref_file.read_text(encoding="utf-8")
                    else:
                        references[ref_file.stem] = ref_file.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to load reference {ref_file}: {e}")

        return references

    def _load_thresholds(self, skill_path: Path) -> dict[str, Any]:
        """Load thresholds from a skill's references/thresholds.yaml.

        Args:
            skill_path: Path to the skill directory

        Returns:
            Dictionary of threshold configurations
        """
        thresholds_path = skill_path / "references" / "thresholds.yaml"

        if not thresholds_path.exists():
            return {}

        try:
            return yaml.safe_load(thresholds_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning(f"Failed to load thresholds from {thresholds_path}: {e}")
            return {}

    def get_skill_content(self, skill_name: str) -> str:
        """Get the injectable content for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill content formatted for prompt injection, or empty string
        """
        skill = self.load_skill(skill_name)
        if skill:
            return skill.get_injectable_content()
        return ""

    def get_thresholds(self, skill_name: str) -> dict[str, Any]:
        """Get thresholds configuration for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Thresholds dictionary or empty dict
        """
        skill = self.load_skill(skill_name)
        if skill:
            return skill.thresholds
        return {}

    def get_abstention_thresholds(self, skill_name: str) -> tuple[float, float]:
        """Get abstention thresholds for a skill.

        Convenience method to get distance_threshold and min_query_coverage.

        Args:
            skill_name: Name of the skill

        Returns:
            Tuple of (distance_threshold, min_query_coverage) with defaults
        """
        thresholds = self.get_thresholds(skill_name)
        abstention = thresholds.get("abstention", {})

        distance_threshold = abstention.get("distance_threshold", 0.5)
        min_query_coverage = abstention.get("min_query_coverage", 0.2)

        return distance_threshold, min_query_coverage

    def get_retrieval_limits(self, skill_name: str) -> dict[str, int]:
        """Get retrieval limits for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Dictionary mapping collection type to limit
        """
        thresholds = self.get_thresholds(skill_name)
        return thresholds.get("retrieval_limits", {
            "adr": 8,
            "principle": 6,
            "policy": 4,
            "vocabulary": 4,
        })

    def get_truncation(self, skill_name: str) -> dict[str, int]:
        """Get content truncation limits for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Dictionary with truncation limits
        """
        thresholds = self.get_thresholds(skill_name)
        return thresholds.get("truncation", {
            "content_max_chars": 800,
            "elysia_content_chars": 500,
            "elysia_summary_chars": 300,
        })

    def clear_cache(self):
        """Clear the skill cache."""
        self._cache.clear()
