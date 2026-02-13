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
from ..doc_type_classifier import (
    DocType,
    REGISTRY_FILENAMES as _CLASSIFIER_REGISTRY_FILENAMES,
    classify_adr_document,
    classify_principle_document,
)

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

# Document types to skip at ingestion time (not embedded, saves tokens/storage)
# =============================================================================
# SKIP RULES:
#   - template: Files with placeholders (adr-template.md, etc.)
#   - index: Directory-level indexes inside decisions/ and principles/
#
# NOT SKIPPED (intentionally ingested):
#   - registry: The top-level doc registry (esa_doc_registry.md)
#     This is the renamed /doc/index.md - human-authored, canonical documentation
#     Classified as "registry" not "index" to avoid accidental skipping
#
# Note: index.md files are still parsed for ownership metadata via index_metadata_loader
# Note: DARs (decision_approval_record) ARE embedded - they're excluded at query time
# =============================================================================
SKIP_DOC_TYPES_AT_INGESTION = set(DocType.skip_at_ingestion_types())

# Registry filenames - imported from doc_type_classifier (single source of truth)
REGISTRY_FILENAMES = _CLASSIFIER_REGISTRY_FILENAMES


def _clean_frontmatter_status(metadata: dict) -> str:
    """Extract and clean status string from frontmatter metadata.

    Handles both top-level 'status' key and quoted values.
    """
    val = metadata.get("status", "")
    if val and isinstance(val, str):
        return val.strip().strip('"').strip("'")
    return ""


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

    # Enriched metadata (P2)
    canonical_id: str = ""  # "ADR.22" or "PCP.22" or "ADR.22D" etc.
    date: str = ""  # From frontmatter
    doc_uuid: str = ""  # From frontmatter dct.identifier
    dar_path: str = ""  # Path to corresponding DAR file

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
            # Enriched metadata (P2)
            "canonical_id": self.canonical_id,
            "date": self.date,
            "doc_uuid": self.doc_uuid,
            "dar_path": self.dar_path,
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
        # Include ADR/Principle ID prominently for better retrieval
        # Include both official format (ADR.21) and raw number for flexible querying
        if self.adr_number:
            try:
                num = int(self.adr_number)
                parts.append(f"ADR.{num:02d}")  # Official format: ADR.21
            except ValueError:
                pass
            parts.append(f"ADR-{self.adr_number}")  # Also include raw: ADR-0021
        if self.principle_number:
            try:
                num = int(self.principle_number)
                parts.append(f"PCP.{num:02d}")  # Official format: PCP.21
            except ValueError:
                pass
            parts.append(f"PCP-{self.principle_number}")  # Also include raw: PCP-0021
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
        r"^#{2,4}\s*Consequences(?:\s+and\s+Trade-offs|\s*&\s*Trade-offs)?\s*\n+(.+?)(?=\n#{2,3}\s|\Z)",
        re.MULTILINE | re.DOTALL,
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

        Skips template and index files at ingestion time to save embedding
        tokens and storage. These are filtered at query time anyway, so
        embedding them provides no value.

        Note: DARs (decision_approval_record) ARE embedded - they contain
        governance info needed for "who approved?" queries.

        Args:
            adr_path: Path to ADR directory

        Yields:
            Dictionary representations of ADRs (excluding templates/indexes)
        """
        adr_files = sorted(adr_path.glob("*.md"))
        logger.info(f"Found {len(adr_files)} ADR files to process")

        skipped_count = 0
        for adr_file in adr_files:
            try:
                doc = self._load_adr(adr_file)
                if doc:
                    # Skip templates and indexes at ingestion time
                    if doc.doc_type in SKIP_DOC_TYPES_AT_INGESTION:
                        logger.debug(f"Skipping {doc.doc_type} at ingestion: {adr_file.name}")
                        skipped_count += 1
                        continue
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading ADR {adr_file}: {e}")
                continue

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} template/index files at ingestion")

    def load_principles(self, principles_path: Path) -> Iterator[dict]:
        """Load principle documents.

        Skips template and index files at ingestion time to save embedding
        tokens and storage. These are filtered at query time anyway, so
        embedding them provides no value.

        Args:
            principles_path: Path to principles directory

        Yields:
            Dictionary representations of principles (excluding templates/indexes)
        """
        principle_files = sorted(principles_path.glob("*.md"))
        logger.info(f"Found {len(principle_files)} principle files to process")

        skipped_count = 0
        for principle_file in principle_files:
            try:
                doc = self._load_principle(principle_file)
                if doc:
                    # Skip templates and indexes at ingestion time
                    if doc.doc_type in SKIP_DOC_TYPES_AT_INGESTION:
                        logger.debug(f"Skipping {doc.doc_type} at ingestion: {principle_file.name}")
                        skipped_count += 1
                        continue
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading principle {principle_file}: {e}")
                continue

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} template/index files at ingestion")

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

    @staticmethod
    def _compute_dar_path(file_path: Path, doc_number: str) -> str:
        """Compute the path to the corresponding Decision Approval Record.

        For a content file like 0022-title.md, the DAR is 0022D-title.md in the same dir.
        For a DAR file, returns its own path (it IS the DAR).

        # TODO: returns absolute paths (e.g., /Users/.../0024D-use-standard-...md).
        # Make relative to repo root for portability across machines.

        Args:
            file_path: Path to the content or DAR file
            doc_number: 4-digit document number

        Returns:
            Path to the DAR file, or empty string if not found
        """
        filename = file_path.name
        # If this IS a DAR file, return its own path
        if re.match(r"^\d{4}[dD]-", filename):
            return str(file_path)

        # Compute DAR filename: replace "NNNN-" with "NNNND-"
        dar_filename = filename.replace(f"{doc_number}-", f"{doc_number}D-", 1)
        dar_path = file_path.parent / dar_filename
        if dar_path.exists():
            return str(dar_path)
        return ""

    def _format_adr_id(self, adr_number: str) -> str:
        """Format ADR number to official ID format (ADR.XX).

        Converts 4-digit number to official format:
        - "0000" -> "ADR.00"
        - "0012" -> "ADR.12"
        - "0021" -> "ADR.21"

        Args:
            adr_number: 4-digit ADR number string

        Returns:
            Formatted ID like "ADR.21"
        """
        if not adr_number:
            return ""
        try:
            num = int(adr_number)
            return f"ADR.{num:02d}"
        except ValueError:
            return f"ADR.{adr_number}"

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

        # Classify via canonical classifier (single source of truth)
        result = classify_adr_document(file_path, doc.title, doc.content)
        doc.doc_type = result.doc_type

        # Enriched metadata (P2): canonical_id, date, uuid, dar_path
        # TODO: update when PRINCIPLE_APPROVAL is added to DocType
        is_dar = doc.doc_type == DocType.ADR_APPROVAL
        if adr_number:
            adr_id = self._format_adr_id(adr_number)
            doc.canonical_id = f"{adr_id}D" if is_dar else adr_id
            doc.dar_path = self._compute_dar_path(file_path, adr_number)
        doc.date = str(doc.metadata.get("date", ""))
        dct = doc.metadata.get("dct", {})
        if isinstance(dct, dict):
            doc.doc_uuid = dct.get("identifier", "")
        fm_status = _clean_frontmatter_status(doc.metadata)

        # Prepend ADR ID to title for better retrieval (using official format ADR.XX)
        # Use different prefix for Decision Approval Records
        if adr_number and not doc.title.lower().startswith("adr"):
            adr_id = self._format_adr_id(adr_number)
            if is_dar:
                doc.title = f"{adr_id}D (Approval Record): {doc.title}"
            else:
                doc.title = f"{adr_id}: {doc.title}"

        # Extract ADR-specific sections
        content = doc.content

        status_match = self.ADR_STATUS_PATTERN.search(content)
        if status_match:
            doc.status = status_match.group(1).strip()
        elif fm_status:
            doc.status = fm_status

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

    def _format_principle_id(self, principle_number: str) -> str:
        """Format Principle number to official ID format (PCP.XX).

        Converts 4-digit number to official format:
        - "0010" -> "PCP.10"
        - "0021" -> "PCP.21"

        Args:
            principle_number: 4-digit principle number string

        Returns:
            Formatted ID like "PCP.21"
        """
        if not principle_number:
            return ""
        try:
            num = int(principle_number)
            return f"PCP.{num:02d}"
        except ValueError:
            return f"PCP.{principle_number}"

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

        # Classify via canonical classifier (single source of truth)
        result = classify_principle_document(file_path, doc.title, doc.content)
        doc.doc_type = result.doc_type

        # Enriched metadata (P2): canonical_id, status, date, uuid, dar_path
        # TODO: update when PRINCIPLE_APPROVAL is added to DocType
        is_dar = doc.doc_type == DocType.ADR_APPROVAL
        if principle_number:
            pcp_id = self._format_principle_id(principle_number)
            doc.canonical_id = f"{pcp_id}D" if is_dar else pcp_id
            doc.dar_path = self._compute_dar_path(file_path, principle_number)
        # Status from frontmatter (principles use dct.isVersionOf or status)
        dct = doc.metadata.get("dct", {})
        if isinstance(dct, dict):
            doc.doc_uuid = dct.get("identifier", "")
            doc.status = dct.get("isVersionOf", "")
        if not doc.status:
            doc.status = _clean_frontmatter_status(doc.metadata)
        # Date from frontmatter (principles use dct.issued or date)
        if isinstance(dct, dict) and dct.get("issued"):
            doc.date = str(dct["issued"])
        elif doc.metadata.get("date"):
            doc.date = str(doc.metadata["date"])

        # Prepend Principle ID to title for better retrieval (using official format PCP.XX)
        # Use different prefix for Decision Approval Records
        if principle_number and not doc.title.lower().startswith("pcp"):
            pcp_id = self._format_principle_id(principle_number)
            if is_dar:
                doc.title = f"{pcp_id}D (Approval Record): {doc.title}"
            else:
                doc.title = f"{pcp_id}: {doc.title}"

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
                fm_metadata = {}
                try:
                    post = frontmatter.loads(content)
                    fm_metadata = dict(post.metadata)
                    body = post.content
                except Exception:
                    body = content

                title = self._extract_title(body, adr_file)
                index_metadata = get_document_metadata(adr_file)

                # Enrich with P2 metadata
                adr_number = self._extract_adr_number(adr_file)
                result = classify_adr_document(adr_file, title, body)
                is_dar = result.doc_type == DocType.ADR_APPROVAL
                if adr_number:
                    adr_id = self._format_adr_id(adr_number)
                    index_metadata["canonical_id"] = f"{adr_id}D" if is_dar else adr_id
                    index_metadata["dar_path"] = self._compute_dar_path(adr_file, adr_number)
                index_metadata["date"] = str(fm_metadata.get("date", ""))
                dct = fm_metadata.get("dct", {})
                if isinstance(dct, dict):
                    index_metadata["doc_uuid"] = dct.get("identifier", "")
                fm_status = _clean_frontmatter_status(fm_metadata)
                if fm_status:
                    index_metadata["status"] = fm_status

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
                fm_metadata = {}
                try:
                    post = frontmatter.loads(content)
                    fm_metadata = dict(post.metadata)
                    body = post.content
                except Exception:
                    body = content

                title = self._extract_title(body, principle_file)
                index_metadata = get_document_metadata(principle_file)

                # Enrich with P2 metadata
                principle_number = self._extract_principle_number(principle_file)
                result = classify_principle_document(principle_file, title, body)
                is_dar = result.doc_type == DocType.ADR_APPROVAL
                if principle_number:
                    pcp_id = self._format_principle_id(principle_number)
                    index_metadata["canonical_id"] = f"{pcp_id}D" if is_dar else pcp_id
                    index_metadata["dar_path"] = self._compute_dar_path(principle_file, principle_number)
                dct = fm_metadata.get("dct", {})
                if isinstance(dct, dict):
                    index_metadata["doc_uuid"] = dct.get("identifier", "")
                    index_metadata["status"] = dct.get("isVersionOf", "")
                    if dct.get("issued"):
                        index_metadata["date"] = str(dct["issued"])
                if not index_metadata.get("status"):
                    fm_status = _clean_frontmatter_status(fm_metadata)
                    if fm_status:
                        index_metadata["status"] = fm_status
                if not index_metadata.get("date") and fm_metadata.get("date"):
                    index_metadata["date"] = str(fm_metadata["date"])

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
