"""Document loader for DOCX and PDF files."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class PolicyDocument:
    """Represents a parsed policy document."""

    file_path: str
    title: str
    content: str
    doc_type: str = "policy"
    file_type: str = ""  # 'docx' or 'pdf'
    page_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        return {
            "file_path": self.file_path,
            "title": self.title,
            "content": self.content,
            "doc_type": self.doc_type,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "full_text": f"Policy: {self.title}\n\n{self.content}",
        }


class DocumentLoader:
    """Loader for DOCX and PDF policy documents."""

    def __init__(self, documents_path: Path):
        """Initialize the document loader.

        Args:
            documents_path: Path to directory containing documents
        """
        self.documents_path = Path(documents_path)

    def load_all(self) -> Iterator[dict]:
        """Load all DOCX and PDF files.

        Yields:
            Dictionary representations of parsed documents
        """
        # Load DOCX files
        docx_files = list(self.documents_path.glob("*.docx"))
        pdf_files = list(self.documents_path.glob("*.pdf"))

        logger.info(
            f"Found {len(docx_files)} DOCX and {len(pdf_files)} PDF files to process"
        )

        for docx_file in docx_files:
            try:
                doc = self._load_docx(docx_file)
                if doc:
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading DOCX {docx_file}: {e}")
                continue

        for pdf_file in pdf_files:
            try:
                doc = self._load_pdf(pdf_file)
                if doc:
                    yield doc.to_dict()
            except Exception as e:
                logger.error(f"Error loading PDF {pdf_file}: {e}")
                continue

    def _load_docx(self, file_path: Path) -> Optional[PolicyDocument]:
        """Load a DOCX file.

        Args:
            file_path: Path to the DOCX file

        Returns:
            Parsed PolicyDocument or None
        """
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx not installed. Run: pip install python-docx")
            return None

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

            # Extract title from filename or first paragraph
            title = self._extract_title(file_path, paragraphs)

            # Extract metadata from core properties
            metadata = {}
            if doc.core_properties:
                if doc.core_properties.author:
                    metadata["author"] = doc.core_properties.author
                if doc.core_properties.created:
                    metadata["created"] = str(doc.core_properties.created)
                if doc.core_properties.modified:
                    metadata["modified"] = str(doc.core_properties.modified)

            return PolicyDocument(
                file_path=str(file_path),
                title=title,
                content=content,
                file_type="docx",
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to parse DOCX {file_path}: {e}")
            return None

    def _load_pdf(self, file_path: Path) -> Optional[PolicyDocument]:
        """Load a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            Parsed PolicyDocument or None
        """
        # Try PyMuPDF first (better extraction)
        try:
            return self._load_pdf_pymupdf(file_path)
        except ImportError:
            pass

        # Fall back to PyPDF2
        try:
            return self._load_pdf_pypdf2(file_path)
        except ImportError:
            logger.error(
                "Neither pymupdf nor PyPDF2 installed. "
                "Run: pip install pymupdf or pip install PyPDF2"
            )
            return None

    def _load_pdf_pymupdf(self, file_path: Path) -> Optional[PolicyDocument]:
        """Load PDF using PyMuPDF (fitz).

        Args:
            file_path: Path to the PDF file

        Returns:
            Parsed PolicyDocument or None
        """
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(str(file_path))
            pages = []

            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text.strip())

            content = "\n\n---\n\n".join(pages)
            title = self._extract_title(file_path, pages)

            # Extract metadata
            metadata = {}
            if doc.metadata:
                for key in ["author", "title", "subject", "creator"]:
                    if doc.metadata.get(key):
                        metadata[key] = doc.metadata[key]

            return PolicyDocument(
                file_path=str(file_path),
                title=title,
                content=content,
                file_type="pdf",
                page_count=len(doc),
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to parse PDF with PyMuPDF {file_path}: {e}")
            return None

    def _load_pdf_pypdf2(self, file_path: Path) -> Optional[PolicyDocument]:
        """Load PDF using PyPDF2.

        Args:
            file_path: Path to the PDF file

        Returns:
            Parsed PolicyDocument or None
        """
        from PyPDF2 import PdfReader

        try:
            reader = PdfReader(str(file_path))
            pages = []

            for page in reader.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text.strip())

            content = "\n\n---\n\n".join(pages)
            title = self._extract_title(file_path, pages)

            # Extract metadata
            metadata = {}
            if reader.metadata:
                for key in ["/Author", "/Title", "/Subject", "/Creator"]:
                    if reader.metadata.get(key):
                        metadata[key.lstrip("/")] = reader.metadata[key]

            return PolicyDocument(
                file_path=str(file_path),
                title=title,
                content=content,
                file_type="pdf",
                page_count=len(reader.pages),
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to parse PDF with PyPDF2 {file_path}: {e}")
            return None

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
