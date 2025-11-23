"""Document loader for DOCX and PDF files with chunking support."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# Maximum characters per chunk (roughly 1500 tokens = ~6000 chars)
MAX_CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500


@dataclass
class PolicyDocument:
    """Represents a parsed policy document or chunk."""

    file_path: str
    title: str
    content: str
    doc_type: str = "policy"
    file_type: str = ""  # 'docx' or 'pdf'
    page_count: int = 0
    chunk_index: int = 0
    total_chunks: int = 1
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        # Add chunk info to title if multiple chunks
        title = self.title
        if self.total_chunks > 1:
            title = f"{self.title} (Part {self.chunk_index + 1}/{self.total_chunks})"

        return {
            "file_path": self.file_path,
            "title": title,
            "content": self.content,
            "doc_type": self.doc_type,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "full_text": f"Policy: {title}\n\n{self.content}",
        }


def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks with overlap.

    Args:
        text: Text to chunk
        max_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= max_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + max_size

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + max_size // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                sentence_break = text.rfind(". ", start, end)
                if sentence_break > start + max_size // 2:
                    end = sentence_break + 2

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start with overlap
        start = end - overlap if end < len(text) else len(text)

    return chunks


class DocumentLoader:
    """Loader for DOCX and PDF policy documents with chunking."""

    def __init__(self, documents_path: Path):
        """Initialize the document loader.

        Args:
            documents_path: Path to directory containing documents
        """
        self.documents_path = Path(documents_path)

    def load_all(self) -> Iterator[dict]:
        """Load all DOCX and PDF files, chunking large documents.

        Yields:
            Dictionary representations of parsed document chunks
        """
        # Load DOCX files
        docx_files = list(self.documents_path.glob("*.docx"))
        pdf_files = list(self.documents_path.glob("*.pdf"))

        logger.info(
            f"Found {len(docx_files)} DOCX and {len(pdf_files)} PDF files to process"
        )

        for docx_file in docx_files:
            try:
                for doc_chunk in self._load_docx_chunked(docx_file):
                    yield doc_chunk.to_dict()
            except Exception as e:
                logger.error(f"Error loading DOCX {docx_file}: {e}")
                continue

        for pdf_file in pdf_files:
            try:
                for doc_chunk in self._load_pdf_chunked(pdf_file):
                    yield doc_chunk.to_dict()
            except Exception as e:
                logger.error(f"Error loading PDF {pdf_file}: {e}")
                continue

    def _load_docx_chunked(self, file_path: Path) -> Iterator[PolicyDocument]:
        """Load a DOCX file and yield chunks.

        Args:
            file_path: Path to the DOCX file

        Yields:
            PolicyDocument chunks
        """
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx not installed. Run: pip install python-docx")
            return

        try:
            doc = Document(str(file_path))

            # Extract text from paragraphs
            paragraphs = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    paragraphs.append(text)

            # Extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(
                        cell.text.strip() for cell in row.cells if cell.text.strip()
                    )
                    if row_text:
                        paragraphs.append(row_text)

            content = "\n\n".join(paragraphs)
            title = self._extract_title(file_path, paragraphs)

            # Chunk the content
            chunks = chunk_text(content)
            total_chunks = len(chunks)

            for i, chunk_content in enumerate(chunks):
                yield PolicyDocument(
                    file_path=str(file_path),
                    title=title,
                    content=chunk_content,
                    file_type="docx",
                    chunk_index=i,
                    total_chunks=total_chunks,
                )

        except Exception as e:
            logger.error(f"Failed to parse DOCX {file_path}: {e}")

    def _load_pdf_chunked(self, file_path: Path) -> Iterator[PolicyDocument]:
        """Load a PDF file and yield chunks.

        Args:
            file_path: Path to the PDF file

        Yields:
            PolicyDocument chunks
        """
        # Try PyMuPDF first (better extraction)
        try:
            yield from self._load_pdf_pymupdf_chunked(file_path)
            return
        except ImportError:
            pass

        # Fall back to pypdf (successor to PyPDF2)
        try:
            yield from self._load_pdf_pypdf_chunked(file_path)
        except ImportError:
            logger.error(
                "Neither pymupdf nor pypdf installed. "
                "Run: pip install pymupdf or pip install pypdf"
            )

    def _load_pdf_pymupdf_chunked(self, file_path: Path) -> Iterator[PolicyDocument]:
        """Load PDF using PyMuPDF and yield chunks."""
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(str(file_path))
            pages = []

            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text.strip())

            content = "\n\n".join(pages)
            title = self._extract_title(file_path, pages)
            page_count = len(doc)

            # Chunk the content
            chunks = chunk_text(content)
            total_chunks = len(chunks)

            for i, chunk_content in enumerate(chunks):
                yield PolicyDocument(
                    file_path=str(file_path),
                    title=title,
                    content=chunk_content,
                    file_type="pdf",
                    page_count=page_count,
                    chunk_index=i,
                    total_chunks=total_chunks,
                )

        except Exception as e:
            logger.error(f"Failed to parse PDF with PyMuPDF {file_path}: {e}")

    def _load_pdf_pypdf_chunked(self, file_path: Path) -> Iterator[PolicyDocument]:
        """Load PDF using pypdf and yield chunks."""
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(file_path))
            pages = []

            for page in reader.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text.strip())

            content = "\n\n".join(pages)
            title = self._extract_title(file_path, pages)
            page_count = len(reader.pages)

            # Chunk the content
            chunks = chunk_text(content)
            total_chunks = len(chunks)

            for i, chunk_content in enumerate(chunks):
                yield PolicyDocument(
                    file_path=str(file_path),
                    title=title,
                    content=chunk_content,
                    file_type="pdf",
                    page_count=page_count,
                    chunk_index=i,
                    total_chunks=total_chunks,
                )

        except Exception as e:
            logger.error(f"Failed to parse PDF with pypdf {file_path}: {e}")

    def _extract_title(self, file_path: Path, paragraphs: list[str]) -> str:
        """Extract title from filename or first paragraph.

        Args:
            file_path: Path to the file
            paragraphs: List of extracted paragraphs

        Returns:
            Extracted title
        """
        # Try to get title from first short paragraph (likely a heading)
        for para in paragraphs[:3]:
            if len(para) < 100 and para.strip():
                return para.strip()

        # Fall back to filename
        return file_path.stem.replace("-", " ").replace("_", " ").title()
