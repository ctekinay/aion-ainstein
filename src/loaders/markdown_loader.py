"""Markdown document loader for ADRs and principles.

Supports two modes:
1. Legacy mode: Loads full documents without chunking (backward compatible)
2. Chunked mode: Uses hierarchical, section-based chunking (recommended)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import frontmatter

from .index_metadata_loader import get_document_metadata

# Import chunking module (optional, for enhanced chunking)
try:
    from ..chunking import (
        ADRChunkingStrategy,
        PrincipleChunkingStrategy,
        ChunkingConfig,
        Chunk,
        ChunkedDocument,
    )
    CHUNKING_AVAILABLE = True
except ImportError:
    CHUNKING_AVAILABLE = False

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
    adr_number: str = ""  # Extracted from filename (e.g., "0012")

    # Principle-specific fields
    principle_number: str = ""  # Extracted from filename (e.g., "0010")

    # Ownership fields from index.md
    owner_team: str = ""
    owner_team_abbr: str = ""
    owner_department: str = ""
    owner_organization: str = ""
    owner_display: str = ""
    collection_name: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        result = {
            "file_path": self.file_path,
            "title": self.title,
            "content": self.content,
            "doc_type": self.doc_type,
            "status": self.status,
            "decision": self.decision,
            "context": self.context,
            "consequences": self.consequences,
            "adr_number": self.adr_number,
            "principle_number": self.principle_number,
            # Ownership fields
            "owner_team": self.owner_team,
            "owner_team_abbr": self.owner_team_abbr,
            "owner_department": self.owner_department,
            "owner_organization": self.owner_organization,
            "owner_display": self.owner_display,
            "collection_name": self.collection_name,
            # Combined searchable text
            "full_text": self._build_full_text(),
        }
        return result

    def _build_full_text(self) -> str:
        """Build full searchable text."""
        parts = []
        # Include ADR/Principle number prominently for better retrieval
        if self.adr_number:
            parts.append(f"ADR-{self.adr_number}")
        if self.principle_number:
            parts.append(f"PCP-{self.principle_number}")
        parts.append(f"Title: {self.title}")
        if self.doc_type:
            parts.append(f"Type: {self.doc_type}")
        if self.status:
            parts.append(f"Status: {self.status}")
        if self.owner_display:
            parts.append(f"Owner: {self.owner_display}")
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

        # Get ownership metadata from index.md
        index_metadata = get_document_metadata(file_path)

        return MarkdownDocument(
            file_path=str(file_path),
            title=title,
            content=body.strip(),
            doc_type=doc_type,
            metadata=metadata,
            owner_team=index_metadata.get("owner_team", ""),
            owner_team_abbr=index_metadata.get("owner_team_abbr", ""),
            owner_department=index_metadata.get("owner_department", ""),
            owner_organization=index_metadata.get("owner_organization", ""),
            owner_display=index_metadata.get("owner_display", ""),
            collection_name=index_metadata.get("collection_name", ""),
        )

    def _classify_adr_document(self, file_path: Path, title: str, content: str) -> str:
        """Classify an ADR document as content, index, or template.

        Args:
            file_path: Path to the ADR file
            title: Document title
            content: Document content

        Returns:
            Classification: 'content', 'index', or 'template'
        """
        file_name = file_path.name.lower()
        title_lower = title.lower()

        # Index files: contain lists of documents, no actual decisions
        index_patterns = ['index.md', 'readme.md', 'overview.md', '_index.md']
        if file_name in index_patterns:
            return 'index'

        # Template files: contain placeholders, not actual content
        template_indicators = [
            '{short title',
            '{problem statement}',
            '{context}',
            '{decision outcome}',
            'template',
            '[insert ',
            '{insert ',
        ]
        if any(ind in title_lower or ind in content.lower() for ind in template_indicators):
            return 'template'

        # Index-like content: lists of other documents
        index_content_indicators = [
            'decision approval record list',
            'energy system architecture - decision records',
            'list of decisions',
            'decision record list',
        ]
        if any(ind in title_lower for ind in index_content_indicators):
            return 'index'

        # Default: actual content document
        return 'content'

    # Regex pattern for extracting ADR number from filename
    ADR_NUMBER_PATTERN = re.compile(r"^(\d{4})D?-")

    def _extract_adr_number(self, file_path: Path) -> str:
        """Extract ADR number from filename.

        Handles both ADR files (0012-name.md) and Decision Record files (0012D-name.md).

        Args:
            file_path: Path to the ADR file

        Returns:
            ADR number as string (e.g., "0012") or empty string if not found
        """
        match = self.ADR_NUMBER_PATTERN.match(file_path.name)
        if match:
            return match.group(1)

        # Also check nav_order in metadata for backup
        return ""

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

        # Extract ADR number from filename
        adr_number = self._extract_adr_number(file_path)
        doc.adr_number = adr_number

        # Prepend ADR number to title for better retrieval
        if adr_number and not doc.title.lower().startswith("adr"):
            doc.title = f"ADR-{adr_number}: {doc.title}"

        # Classify as content, index, or template
        doc.doc_type = self._classify_adr_document(file_path, doc.title, doc.content)

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

    def _classify_principle_document(self, file_path: Path, title: str, content: str) -> str:
        """Classify a principle document as content, index, or template.

        Args:
            file_path: Path to the principle file
            title: Document title
            content: Document content

        Returns:
            Classification: 'content', 'index', or 'template'
        """
        file_name = file_path.name.lower()
        title_lower = title.lower()

        # Index files
        index_patterns = ['index.md', 'readme.md', 'overview.md', '_index.md']
        if file_name in index_patterns:
            return 'index'

        # Template files
        template_indicators = [
            'template',
            '{title}',
            '{description}',
            '[insert ',
            '{insert ',
            'principle-template',
            'principle-decision-template',
        ]
        if any(ind in file_name or ind in title_lower for ind in template_indicators):
            return 'template'

        # Default: actual content
        return 'content'

    # Regex pattern for extracting Principle number from filename
    PRINCIPLE_NUMBER_PATTERN = re.compile(r"^(\d{4})D?-")

    def _extract_principle_number(self, file_path: Path) -> str:
        """Extract Principle number from filename.

        Handles both Principle files (0010-name.md) and Decision Record files (0010D-name.md).

        Args:
            file_path: Path to the principle file

        Returns:
            Principle number as string (e.g., "0010") or empty string if not found
        """
        match = self.PRINCIPLE_NUMBER_PATTERN.match(file_path.name)
        if match:
            return match.group(1)
        return ""

    def _load_principle(self, file_path: Path) -> Optional[MarkdownDocument]:
        """Load a principle document.

        Args:
            file_path: Path to the principle file

        Returns:
            Parsed MarkdownDocument
        """
        doc = self._load_file(file_path)
        if not doc:
            return None

        # Extract Principle number from filename
        principle_number = self._extract_principle_number(file_path)
        doc.principle_number = principle_number

        # Prepend Principle number to title for better retrieval
        if principle_number and not doc.title.lower().startswith("pcp"):
            doc.title = f"PCP-{principle_number}: {doc.title}"

        # Classify as content, index, or template
        doc.doc_type = self._classify_principle_document(file_path, doc.title, doc.content)

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

    # ========== Chunked Loading Methods (New) ==========

    def load_adrs_chunked(
        self,
        adr_path: Path,
        config: Optional["ChunkingConfig"] = None,
    ) -> Iterator["ChunkedDocument"]:
        """Load ADRs with hierarchical section-based chunking.

        This method creates multiple chunks per ADR:
        - Section-level chunks (Context, Decision, Consequences)
        - Granular chunks for large sections

        Args:
            adr_path: Path to ADR directory
            config: Optional chunking configuration

        Yields:
            ChunkedDocument objects with hierarchical chunks
        """
        if not CHUNKING_AVAILABLE:
            logger.warning("Chunking module not available. Use load_adrs() instead.")
            return

        strategy = ADRChunkingStrategy(config)
        adr_files = sorted(adr_path.glob("*.md"))
        logger.info(f"Loading {len(adr_files)} ADR files with chunking")

        for adr_file in adr_files:
            try:
                content = adr_file.read_text(encoding="utf-8")

                # Parse frontmatter
                try:
                    post = frontmatter.loads(content)
                    body = post.content
                except Exception:
                    body = content

                title = self._extract_title(body, adr_file)
                index_metadata = get_document_metadata(adr_file)

                chunked_doc = strategy.chunk_document(
                    content=body,
                    file_path=str(adr_file),
                    title=title,
                    metadata=index_metadata,
                )

                logger.debug(
                    f"Chunked ADR '{title}' into {chunked_doc.total_chunks} chunks"
                )
                yield chunked_doc

            except Exception as e:
                logger.error(f"Error chunking ADR {adr_file}: {e}")
                continue

    def load_principles_chunked(
        self,
        principles_path: Path,
        config: Optional["ChunkingConfig"] = None,
    ) -> Iterator["ChunkedDocument"]:
        """Load principles with hierarchical section-based chunking.

        Args:
            principles_path: Path to principles directory
            config: Optional chunking configuration

        Yields:
            ChunkedDocument objects with hierarchical chunks
        """
        if not CHUNKING_AVAILABLE:
            logger.warning("Chunking module not available. Use load_principles() instead.")
            return

        strategy = PrincipleChunkingStrategy(config)
        principle_files = sorted(principles_path.glob("*.md"))
        logger.info(f"Loading {len(principle_files)} principle files with chunking")

        for principle_file in principle_files:
            try:
                content = principle_file.read_text(encoding="utf-8")

                # Parse frontmatter
                try:
                    post = frontmatter.loads(content)
                    body = post.content
                except Exception:
                    body = content

                title = self._extract_title(body, principle_file)
                index_metadata = get_document_metadata(principle_file)

                chunked_doc = strategy.chunk_document(
                    content=body,
                    file_path=str(principle_file),
                    title=title,
                    metadata=index_metadata,
                )

                logger.debug(
                    f"Chunked principle '{title}' into {chunked_doc.total_chunks} chunks"
                )
                yield chunked_doc

            except Exception as e:
                logger.error(f"Error chunking principle {principle_file}: {e}")
                continue

    def load_all_chunked(
        self,
        config: Optional["ChunkingConfig"] = None,
    ) -> Iterator["ChunkedDocument"]:
        """Load all markdown files with appropriate chunking strategy.

        Automatically detects document type and applies the correct
        chunking strategy (ADR or Principle).

        Args:
            config: Optional chunking configuration

        Yields:
            ChunkedDocument objects
        """
        if not CHUNKING_AVAILABLE:
            logger.warning("Chunking module not available. Use load_all() instead.")
            return

        md_files = list(self.base_path.rglob("*.md"))
        logger.info(f"Loading {len(md_files)} markdown files with chunking")

        for md_file in md_files:
            try:
                doc_type = self._determine_doc_type(md_file)

                if doc_type == "adr":
                    strategy = ADRChunkingStrategy(config)
                elif doc_type == "principle":
                    strategy = PrincipleChunkingStrategy(config)
                else:
                    # Use principle strategy as default for other markdown
                    strategy = PrincipleChunkingStrategy(config)

                content = md_file.read_text(encoding="utf-8")

                try:
                    post = frontmatter.loads(content)
                    body = post.content
                except Exception:
                    body = content

                title = self._extract_title(body, md_file)
                index_metadata = get_document_metadata(md_file)

                chunked_doc = strategy.chunk_document(
                    content=body,
                    file_path=str(md_file),
                    title=title,
                    metadata=index_metadata,
                )

                yield chunked_doc

            except Exception as e:
                logger.error(f"Error chunking {md_file}: {e}")
                continue
