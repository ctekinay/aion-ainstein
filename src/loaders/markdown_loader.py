"""Markdown document loader for ADRs and principles."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class MarkdownDocument:
    """Represents a parsed Markdown document."""

    file_path: str
    title: str
    content: str
    doc_type: str  # 'adr', 'principle', 'policy'
    metadata: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)

    # ADR-specific fields
    status: str = ""
    decision: str = ""
    context: str = ""
    consequences: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        return {
            "file_path": self.file_path,
            "title": self.title,
            "content": self.content,
            "doc_type": self.doc_type,
            "status": self.status,
            "decision": self.decision,
            "context": self.context,
            "consequences": self.consequences,
            "metadata": self.metadata,
            # Combined searchable text
            "full_text": self._build_full_text(),
        }

    def _build_full_text(self) -> str:
        """Build full searchable text."""
        parts = [f"Title: {self.title}"]
        if self.doc_type:
            parts.append(f"Type: {self.doc_type}")
        if self.status:
            parts.append(f"Status: {self.status}")
        parts.append(f"\n{self.content}")
        return "\n".join(parts)


class MarkdownLoader:
    """Loader for Markdown documents including ADRs and principles."""

    # Regex patterns for ADR parsing
    ADR_STATUS_PATTERN = re.compile(
        r"^##?\s*Status\s*\n+(.+?)(?=\n##|\n\*\*|\Z)", re.MULTILINE | re.DOTALL
    )
    ADR_CONTEXT_PATTERN = re.compile(
        r"^##?\s*Context(?:\s+and\s+Problem\s+Statement)?\s*\n+(.+?)(?=\n##|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    ADR_DECISION_PATTERN = re.compile(
        r"^##?\s*Decision(?:\s+Outcome)?\s*\n+(.+?)(?=\n##|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    ADR_CONSEQUENCES_PATTERN = re.compile(
        r"^##?\s*Consequences\s*\n+(.+?)(?=\n##|\Z)", re.MULTILINE | re.DOTALL
    )

    def __init__(self, base_path: Path):
        """Initialize the Markdown loader.

        Args:
            base_path: Base path for Markdown documents
        """
        self.base_path = Path(base_path)

    def load_all(self) -> Iterator[dict]:
        """Load all Markdown files and yield documents.

        Yields:
            Dictionary representations of parsed documents
        """
        md_files = list(self.base_path.rglob("*.md"))
        logger.info(f"Found {len(md_files)} Markdown files to process")

        for md_file in md_files:
            try:
                doc = self._load_file(md_file)
                if doc:
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading {md_file}: {e}")
                continue

    def load_adrs(self, adr_path: Path) -> Iterator[dict]:
        """Load Architectural Decision Records.

        Args:
            adr_path: Path to ADR directory

        Yields:
            Dictionary representations of ADRs
        """
        adr_files = sorted(adr_path.glob("*.md"))
        logger.info(f"Found {len(adr_files)} ADR files to process")

        for adr_file in adr_files:
            try:
                doc = self._load_adr(adr_file)
                if doc:
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading ADR {adr_file}: {e}")
                continue

    def load_principles(self, principles_path: Path) -> Iterator[dict]:
        """Load principle documents.

        Args:
            principles_path: Path to principles directory

        Yields:
            Dictionary representations of principles
        """
        principle_files = sorted(principles_path.glob("*.md"))
        logger.info(f"Found {len(principle_files)} principle files to process")

        for principle_file in principle_files:
            try:
                doc = self._load_principle(principle_file)
                if doc:
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading principle {principle_file}: {e}")
                continue

    def _load_file(self, file_path: Path) -> Optional[MarkdownDocument]:
        """Load a single Markdown file.

        Args:
            file_path: Path to the Markdown file

        Returns:
            Parsed MarkdownDocument or None
        """
        content = file_path.read_text(encoding="utf-8")

        # Try to parse frontmatter
        try:
            post = frontmatter.loads(content)
            metadata = dict(post.metadata)
            body = post.content
        except Exception:
            metadata = {}
            body = content

        # Extract title from first heading or filename
        title = self._extract_title(body, file_path)

        # Determine document type based on path
        doc_type = self._determine_doc_type(file_path)

        return MarkdownDocument(
            file_path=str(file_path),
            title=title,
            content=body.strip(),
            doc_type=doc_type,
            metadata=metadata,
        )

    def _load_adr(self, file_path: Path) -> Optional[MarkdownDocument]:
        """Load an Architectural Decision Record.

        Args:
            file_path: Path to the ADR file

        Returns:
            Parsed MarkdownDocument with ADR fields
        """
        doc = self._load_file(file_path)
        if not doc:
            return None

        doc.doc_type = "adr"

        # Extract ADR-specific sections
        content = doc.content

        status_match = self.ADR_STATUS_PATTERN.search(content)
        if status_match:
            doc.status = status_match.group(1).strip()

        context_match = self.ADR_CONTEXT_PATTERN.search(content)
        if context_match:
            doc.context = context_match.group(1).strip()

        decision_match = self.ADR_DECISION_PATTERN.search(content)
        if decision_match:
            doc.decision = decision_match.group(1).strip()

        consequences_match = self.ADR_CONSEQUENCES_PATTERN.search(content)
        if consequences_match:
            doc.consequences = consequences_match.group(1).strip()

        return doc

    def _load_principle(self, file_path: Path) -> Optional[MarkdownDocument]:
        """Load a principle document.

        Args:
            file_path: Path to the principle file

        Returns:
            Parsed MarkdownDocument
        """
        doc = self._load_file(file_path)
        if doc:
            doc.doc_type = "principle"
        return doc

    def _extract_title(self, content: str, file_path: Path) -> str:
        """Extract title from content or filename.

        Args:
            content: Markdown content
            file_path: File path for fallback

        Returns:
            Extracted title
        """
        # Look for first heading
        heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()

        # Use filename without extension
        return file_path.stem.replace("-", " ").replace("_", " ").title()

    def _determine_doc_type(self, file_path: Path) -> str:
        """Determine document type from file path.

        Args:
            file_path: Path to the file

        Returns:
            Document type string
        """
        path_str = str(file_path).lower()

        if "decisions" in path_str or "adr" in path_str:
            return "adr"
        elif "principles" in path_str:
            return "principle"
        elif "policy" in path_str:
            return "policy"
        else:
            return "document"
