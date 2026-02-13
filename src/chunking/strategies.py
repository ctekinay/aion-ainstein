"""Document-type specific chunking strategies.

Each document type (ADR, Principle, Policy) has its own chunking strategy
that respects the document's natural structure.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .models import Chunk, ChunkedDocument, ChunkMetadata, ChunkType

logger = logging.getLogger(__name__)


# Chunking configuration defaults
DEFAULT_MAX_CHUNK_SIZE = 2000  # chars (~500 tokens)
DEFAULT_MIN_CHUNK_SIZE = 200  # Minimum chunk size to avoid tiny chunks
DEFAULT_OVERLAP = 100  # chars overlap between chunks
LARGE_SECTION_THRESHOLD = 3000  # chars - sections larger than this get subdivided


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE
    overlap: int = DEFAULT_OVERLAP
    large_section_threshold: int = LARGE_SECTION_THRESHOLD

    # What to include in indexing
    index_document_level: bool = False  # Full document as single chunk
    index_section_level: bool = True  # Section-level chunks
    index_granular: bool = True  # Paragraph/semantic chunks


class ChunkingStrategy(ABC):
    """Abstract base class for document-type specific chunking strategies."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    @abstractmethod
    def chunk_document(
        self,
        content: str,
        file_path: str,
        title: str,
        metadata: Optional[dict] = None,
    ) -> ChunkedDocument:
        """Chunk a document according to its type-specific strategy.

        Args:
            content: The document content
            file_path: Path to the source file
            title: Document title
            metadata: Additional metadata (ownership, etc.)

        Returns:
            ChunkedDocument with hierarchical chunks
        """
        pass

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on common Dutch words."""
        dutch_indicators = [
            " de ", " het ", " een ", " van ", " en ", " in ", " is ",
            " dat ", " die ", " voor ", " met ", " op ", " te ", " aan ",
            " wordt ", " worden ", " zijn ", " naar ", " bij ", " ook ",
        ]
        text_lower = text.lower()
        dutch_count = sum(1 for word in dutch_indicators if word in text_lower)

        # If more than 3 Dutch indicators found, consider it Dutch
        return "nl" if dutch_count > 3 else "en"

    def _has_code_block(self, text: str) -> bool:
        """Check if text contains code blocks."""
        return "```" in text or bool(re.search(r"^    .+$", text, re.MULTILINE))

    def _has_table(self, text: str) -> bool:
        """Check if text contains markdown tables."""
        return bool(re.search(r"\|.+\|.+\|", text))

    def _has_list(self, text: str) -> bool:
        """Check if text contains markdown lists."""
        return bool(re.search(r"^[\s]*[-*+]|\d+\.\s", text, re.MULTILINE))

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_large_text(
        self,
        text: str,
        max_size: int = None,
        overlap: int = None,
    ) -> list[str]:
        """Split large text into smaller chunks with overlap.

        Tries to break at natural boundaries (paragraphs, sentences).
        """
        max_size = max_size or self.config.max_chunk_size
        overlap = overlap or self.config.overlap

        if len(text) <= max_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + max_size

            # Try to find a good break point
            if end < len(text):
                # Try paragraph break first
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + max_size // 2:
                    end = para_break + 2
                else:
                    # Try sentence break
                    sentence_break = text.rfind(". ", start, end)
                    if sentence_break > start + max_size // 2:
                        end = sentence_break + 2
                    else:
                        # Try any newline
                        newline_break = text.rfind("\n", start, end)
                        if newline_break > start + max_size // 2:
                            end = newline_break + 1

            chunk = text[start:end].strip()
            if chunk and len(chunk) >= self.config.min_chunk_size:
                chunks.append(chunk)

            # Move start with overlap
            start = end - overlap if end < len(text) else len(text)

        return chunks

    def _create_chunk(
        self,
        content: str,
        chunk_type: ChunkType,
        file_path: str,
        title: str,
        section_name: str = "",
        section_type: str = "",
        position_in_document: int = 0,
        position_in_section: int = 0,
        parent_chunk_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        completeness: float = 1.0,
    ) -> Chunk:
        """Create a chunk with full metadata."""
        meta = ChunkMetadata(
            source_file=file_path,
            document_title=title,
            document_type=self._get_document_type(),
            section_name=section_name,
            section_type=section_type,
            position_in_document=position_in_document,
            position_in_section=position_in_section,
            parent_chunk_id=parent_chunk_id,
            has_code_block=self._has_code_block(content),
            has_table=self._has_table(content),
            has_list=self._has_list(content),
            language=self._detect_language(content),
            completeness=completeness,
        )

        # Apply external metadata (ownership, P2 enrichment, etc.)
        if metadata:
            meta.owner_team = metadata.get("owner_team", "")
            meta.owner_team_abbr = metadata.get("owner_team_abbr", "")
            meta.owner_department = metadata.get("owner_department", "")
            meta.owner_organization = metadata.get("owner_organization", "")
            meta.owner_display = metadata.get("owner_display", "")
            meta.collection_name = metadata.get("collection_name", "")
            # Enriched metadata (P2)
            meta.canonical_id = metadata.get("canonical_id", "")
            meta.status = metadata.get("status", "")
            meta.date = metadata.get("date", "")
            meta.doc_uuid = metadata.get("doc_uuid", "")
            meta.dar_path = metadata.get("dar_path", "")

        chunk = Chunk(
            content=content,
            chunk_type=chunk_type,
            metadata=meta,
        )
        chunk.full_text = chunk.build_full_text()

        return chunk

    @abstractmethod
    def _get_document_type(self) -> str:
        """Return the document type for this strategy."""
        pass


class ADRChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for Architectural Decision Records.

    ADRs have a well-defined structure:
    - Title
    - Status
    - Context (and Problem Statement)
    - Decision (Outcome)
    - Consequences

    This strategy creates:
    1. Section-level chunks for each major section
    2. Granular chunks for large sections
    """

    # Regex patterns for ADR sections
    SECTION_PATTERNS = [
        (r"^##?\s*Status\s*$", "status", "Status"),
        (r"^##?\s*Context(?:\s+and\s+Problem\s+Statement)?\s*$", "context", "Context"),
        (r"^##?\s*Decision(?:\s+Outcome)?\s*$", "decision", "Decision"),
        (r"^#{2,4}\s*Consequences(?:\s+and\s+Trade-offs|\s*&\s*Trade-offs)?\s*$", "consequences", "Consequences"),
        (r"^##?\s*Considered\s+Options?\s*$", "options", "Considered Options"),
        (r"^##?\s*Pros?\s+and\s+Cons?\s*$", "proscons", "Pros and Cons"),
        (r"^##?\s*Links?\s*$", "links", "Links"),
        (r"^##?\s*Notes?\s*$", "notes", "Notes"),
        (r"^##?\s*References?\s*$", "references", "References"),
    ]

    def _get_document_type(self) -> str:
        return "adr"

    def _extract_status(self, content: str) -> str:
        """Extract ADR status from content."""
        status_match = re.search(
            r"^##?\s*Status\s*\n+(.+?)(?=\n##|\n\*\*|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        if status_match:
            status_text = status_match.group(1).strip()
            # Extract just the status word (accepted, deprecated, etc.)
            status_word = re.search(r"\b(accepted|deprecated|superseded|proposed|draft|rejected)\b",
                                    status_text.lower())
            if status_word:
                return status_word.group(1)
        return ""

    def _extract_sections(self, content: str) -> list[tuple[str, str, str, int]]:
        """Extract sections from ADR content.

        Returns list of (section_type, section_name, section_content, start_pos).
        """
        sections = []

        # Find all section headers
        header_pattern = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)
        headers = list(header_pattern.finditer(content))

        for i, match in enumerate(headers):
            header_level = len(match.group(1))
            header_text = match.group(2).strip()
            start_pos = match.end()

            # Find end of section (next header or end of content)
            if i + 1 < len(headers):
                end_pos = headers[i + 1].start()
            else:
                end_pos = len(content)

            section_content = content[start_pos:end_pos].strip()

            # Determine section type
            section_type = "other"
            section_name = header_text

            for pattern, s_type, s_name in self.SECTION_PATTERNS:
                if re.match(pattern, f"{'#' * header_level} {header_text}", re.IGNORECASE):
                    section_type = s_type
                    section_name = s_name
                    break

            if section_content:  # Only add non-empty sections
                sections.append((section_type, section_name, section_content, match.start()))

        return sections

    def chunk_document(
        self,
        content: str,
        file_path: str,
        title: str,
        metadata: Optional[dict] = None,
    ) -> ChunkedDocument:
        """Chunk an ADR into section-based chunks."""
        metadata = metadata or {}
        doc = ChunkedDocument(
            source_file=file_path,
            document_title=title,
            document_type="adr",
            chunking_strategy="adr_section",
        )

        # Extract ADR status
        adr_status = self._extract_status(content)

        # Create document-level chunk (optional, for full-document search)
        if self.config.index_document_level:
            doc_chunk = self._create_chunk(
                content=content,
                chunk_type=ChunkType.DOCUMENT,
                file_path=file_path,
                title=title,
                metadata=metadata,
            )
            doc_chunk.metadata.adr_status = adr_status
            doc.add_chunk(doc_chunk)

        # Extract and process sections
        sections = self._extract_sections(content)
        position = 0

        for section_type, section_name, section_content, _ in sections:
            position += 1

            # Create section-level chunk
            section_chunk = self._create_chunk(
                content=section_content,
                chunk_type=ChunkType.SECTION,
                file_path=file_path,
                title=title,
                section_name=section_name,
                section_type=section_type,
                position_in_document=position,
                metadata=metadata,
            )
            section_chunk.metadata.adr_status = adr_status

            if self.config.index_section_level:
                doc.add_chunk(section_chunk)

            # If section is large, create granular sub-chunks
            if len(section_content) > self.config.large_section_threshold:
                sub_chunks = self._split_large_text(section_content)

                for sub_pos, sub_content in enumerate(sub_chunks):
                    granular_chunk = self._create_chunk(
                        content=sub_content,
                        chunk_type=ChunkType.SEMANTIC_UNIT,
                        file_path=file_path,
                        title=title,
                        section_name=section_name,
                        section_type=section_type,
                        position_in_document=position,
                        position_in_section=sub_pos,
                        parent_chunk_id=section_chunk.id,
                        metadata=metadata,
                        completeness=1.0 if len(sub_chunks) == 1 else 0.8,
                    )
                    granular_chunk.metadata.adr_status = adr_status

                    if self.config.index_granular:
                        doc.add_chunk(granular_chunk)

        # If no sections found, treat whole content as a single chunk
        if not sections:
            fallback_chunk = self._create_chunk(
                content=content,
                chunk_type=ChunkType.SECTION,
                file_path=file_path,
                title=title,
                section_name="Content",
                section_type="content",
                position_in_document=1,
                metadata=metadata,
            )
            fallback_chunk.metadata.adr_status = adr_status
            doc.add_chunk(fallback_chunk)

        return doc


class PrincipleChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for Architecture Principles.

    Principles typically have:
    - Title/Name
    - Statement
    - Rationale
    - Implications/Applications

    Creates section-level chunks for each part.
    """

    SECTION_PATTERNS = [
        (r"^##?\s*Statement\s*$", "statement", "Statement"),
        (r"^##?\s*Rationale\s*$", "rationale", "Rationale"),
        (r"^##?\s*Implications?\s*$", "implications", "Implications"),
        (r"^##?\s*Applications?\s*$", "applications", "Applications"),
        (r"^##?\s*Examples?\s*$", "examples", "Examples"),
        (r"^##?\s*Related\s+Principles?\s*$", "related", "Related Principles"),
        (r"^##?\s*References?\s*$", "references", "References"),
    ]

    def _get_document_type(self) -> str:
        return "principle"

    def _extract_sections(self, content: str) -> list[tuple[str, str, str]]:
        """Extract sections from principle content."""
        sections = []

        header_pattern = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)
        headers = list(header_pattern.finditer(content))

        for i, match in enumerate(headers):
            header_level = len(match.group(1))
            header_text = match.group(2).strip()
            start_pos = match.end()

            if i + 1 < len(headers):
                end_pos = headers[i + 1].start()
            else:
                end_pos = len(content)

            section_content = content[start_pos:end_pos].strip()

            section_type = "other"
            section_name = header_text

            for pattern, s_type, s_name in self.SECTION_PATTERNS:
                if re.match(pattern, f"{'#' * header_level} {header_text}", re.IGNORECASE):
                    section_type = s_type
                    section_name = s_name
                    break

            if section_content:
                sections.append((section_type, section_name, section_content))

        return sections

    def chunk_document(
        self,
        content: str,
        file_path: str,
        title: str,
        metadata: Optional[dict] = None,
    ) -> ChunkedDocument:
        """Chunk a principle document into section-based chunks."""
        metadata = metadata or {}
        doc = ChunkedDocument(
            source_file=file_path,
            document_title=title,
            document_type="principle",
            chunking_strategy="principle_section",
        )

        # Document-level chunk
        if self.config.index_document_level:
            doc_chunk = self._create_chunk(
                content=content,
                chunk_type=ChunkType.DOCUMENT,
                file_path=file_path,
                title=title,
                metadata=metadata,
            )
            doc.add_chunk(doc_chunk)

        # Extract sections
        sections = self._extract_sections(content)
        position = 0

        for section_type, section_name, section_content in sections:
            position += 1

            section_chunk = self._create_chunk(
                content=section_content,
                chunk_type=ChunkType.SECTION,
                file_path=file_path,
                title=title,
                section_name=section_name,
                section_type=section_type,
                position_in_document=position,
                metadata=metadata,
            )

            if self.config.index_section_level:
                doc.add_chunk(section_chunk)

            # Subdivide large sections
            if len(section_content) > self.config.large_section_threshold:
                sub_chunks = self._split_large_text(section_content)

                for sub_pos, sub_content in enumerate(sub_chunks):
                    granular_chunk = self._create_chunk(
                        content=sub_content,
                        chunk_type=ChunkType.SEMANTIC_UNIT,
                        file_path=file_path,
                        title=title,
                        section_name=section_name,
                        section_type=section_type,
                        position_in_document=position,
                        position_in_section=sub_pos,
                        parent_chunk_id=section_chunk.id,
                        metadata=metadata,
                    )

                    if self.config.index_granular:
                        doc.add_chunk(granular_chunk)

        # Fallback for documents without sections
        if not sections:
            fallback_chunk = self._create_chunk(
                content=content,
                chunk_type=ChunkType.SECTION,
                file_path=file_path,
                title=title,
                section_name="Content",
                section_type="content",
                position_in_document=1,
                metadata=metadata,
            )
            doc.add_chunk(fallback_chunk)

        return doc


class PolicyChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for Policy documents (PDF/DOCX).

    Policy documents are typically longer and less structured.
    This strategy:
    1. Detects headers/sections where possible
    2. Falls back to paragraph-based chunking
    3. Uses semantic chunking for very long passages
    """

    def _get_document_type(self) -> str:
        return "policy"

    def _detect_headers(self, content: str) -> list[tuple[int, str, int]]:
        """Detect headers in document content.

        Returns list of (level, header_text, position).
        """
        headers = []

        # Markdown headers
        md_headers = re.finditer(r"^(#{1,3})\s+(.+)$", content, re.MULTILINE)
        for match in md_headers:
            level = len(match.group(1))
            headers.append((level, match.group(2).strip(), match.start()))

        # All-caps lines that look like headers
        caps_headers = re.finditer(r"^([A-Z][A-Z\s]{5,50})$", content, re.MULTILINE)
        for match in caps_headers:
            headers.append((1, match.group(1).strip().title(), match.start()))

        # Sort by position
        headers.sort(key=lambda x: x[2])

        return headers

    def chunk_document(
        self,
        content: str,
        file_path: str,
        title: str,
        metadata: Optional[dict] = None,
    ) -> ChunkedDocument:
        """Chunk a policy document."""
        metadata = metadata or {}
        doc = ChunkedDocument(
            source_file=file_path,
            document_title=title,
            document_type="policy",
            chunking_strategy="policy_hybrid",
        )

        # Document-level chunk
        if self.config.index_document_level:
            doc_chunk = self._create_chunk(
                content=content,
                chunk_type=ChunkType.DOCUMENT,
                file_path=file_path,
                title=title,
                metadata=metadata,
            )
            doc.add_chunk(doc_chunk)

        # Try to detect headers/sections
        headers = self._detect_headers(content)

        if headers:
            # Section-based chunking
            position = 0
            for i, (level, header_text, start_pos) in enumerate(headers):
                # Find end of section
                if i + 1 < len(headers):
                    end_pos = headers[i + 1][2]
                else:
                    end_pos = len(content)

                section_content = content[start_pos:end_pos].strip()
                # Remove the header itself from content
                header_match = re.match(r"^#{1,3}\s+.+\n*|^[A-Z][A-Z\s]+\n*", section_content)
                if header_match:
                    section_content = section_content[header_match.end():].strip()

                if not section_content:
                    continue

                position += 1

                chunk_type = ChunkType.SECTION if level <= 2 else ChunkType.SUBSECTION

                section_chunk = self._create_chunk(
                    content=section_content,
                    chunk_type=chunk_type,
                    file_path=file_path,
                    title=title,
                    section_name=header_text,
                    section_type=f"heading_{level}",
                    position_in_document=position,
                    metadata=metadata,
                )
                section_chunk.metadata.heading_level = level

                if self.config.index_section_level:
                    doc.add_chunk(section_chunk)

                # Subdivide large sections
                if len(section_content) > self.config.large_section_threshold:
                    sub_chunks = self._split_large_text(section_content)

                    for sub_pos, sub_content in enumerate(sub_chunks):
                        granular_chunk = self._create_chunk(
                            content=sub_content,
                            chunk_type=ChunkType.SEMANTIC_UNIT,
                            file_path=file_path,
                            title=title,
                            section_name=header_text,
                            position_in_document=position,
                            position_in_section=sub_pos,
                            parent_chunk_id=section_chunk.id,
                            metadata=metadata,
                        )

                        if self.config.index_granular:
                            doc.add_chunk(granular_chunk)

        else:
            # No headers detected - use paragraph/semantic chunking
            chunks = self._split_large_text(content)

            for position, chunk_content in enumerate(chunks):
                chunk = self._create_chunk(
                    content=chunk_content,
                    chunk_type=ChunkType.SEMANTIC_UNIT,
                    file_path=file_path,
                    title=title,
                    section_name="Content",
                    section_type="content",
                    position_in_document=position + 1,
                    metadata=metadata,
                )
                doc.add_chunk(chunk)

        return doc


class VocabularyChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for vocabulary/ontology concepts.

    Vocabulary items are already atomic (one concept = one chunk),
    so this strategy mainly handles formatting and metadata.
    """

    def _get_document_type(self) -> str:
        return "vocabulary"

    def chunk_document(
        self,
        content: str,
        file_path: str,
        title: str,
        metadata: Optional[dict] = None,
    ) -> ChunkedDocument:
        """Create a single chunk for a vocabulary concept."""
        metadata = metadata or {}
        doc = ChunkedDocument(
            source_file=file_path,
            document_title=title,
            document_type="vocabulary",
            chunking_strategy="vocabulary_atomic",
        )

        chunk = self._create_chunk(
            content=content,
            chunk_type=ChunkType.DOCUMENT,  # Concepts are already atomic
            file_path=file_path,
            title=title,
            metadata=metadata,
        )
        doc.add_chunk(chunk)

        return doc


def get_chunking_strategy(
    document_type: str,
    config: Optional[ChunkingConfig] = None,
) -> ChunkingStrategy:
    """Get the appropriate chunking strategy for a document type.

    Args:
        document_type: Type of document (adr, principle, policy, vocabulary)
        config: Optional chunking configuration

    Returns:
        Appropriate ChunkingStrategy instance
    """
    strategies = {
        "adr": ADRChunkingStrategy,
        "principle": PrincipleChunkingStrategy,
        "policy": PolicyChunkingStrategy,
        "vocabulary": VocabularyChunkingStrategy,
    }

    strategy_class = strategies.get(document_type.lower(), PolicyChunkingStrategy)
    return strategy_class(config)
