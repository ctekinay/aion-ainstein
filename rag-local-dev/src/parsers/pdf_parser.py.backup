"""
PDF and DOCX parser for policy documents.
Uses two-pass parsing with fallback for complex layouts.
"""

import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a parsed chunk from a PDF or DOCX document."""

    content: str
    page_number: Optional[int]
    section_header: Optional[str]
    has_tables: bool
    has_figures: bool
    source_file: str
    chunk_index: int
    document_title: Optional[str] = None
    file_type: str = "pdf"


def detect_section_header(page, toc: list, page_num: int) -> Optional[str]:
    """Detect section header from ToC or page content."""
    # Check ToC for entries on this page
    for level, title, toc_page in toc:
        if toc_page == page_num + 1:
            return title

    # Fallback: look for large/bold text at top of page
    try:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks[:3]:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["size"] > 12 or "bold" in span["font"].lower():
                            text = span["text"].strip()
                            if 3 < len(text) < 100:
                                return text
    except Exception:
        pass

    return None


def extract_tables_pdfplumber(filepath: Path, page_num: int) -> list:
    """Extract tables from specific page using pdfplumber."""
    try:
        with pdfplumber.open(filepath) as pdf:
            if page_num < len(pdf.pages):
                page = pdf.pages[page_num]
                return page.extract_tables() or []
    except Exception as e:
        logger.warning(f"Table extraction failed for page {page_num}: {e}")
    return []


def format_table(table: list) -> str:
    """Convert table to readable text format."""
    if not table:
        return ""

    lines = []
    for row in table:
        cells = [str(cell) if cell else "" for cell in row]
        lines.append(" | ".join(cells))

    return "\n".join(lines)


def fallback_raw_extraction(filepath: Path) -> List[DocumentChunk]:
    """Last resort: just get the text out."""
    doc = fitz.open(filepath)
    chunks = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            chunks.append(
                DocumentChunk(
                    content=text.strip(),
                    page_number=page_num + 1,
                    section_header=None,
                    has_tables=False,
                    has_figures=False,
                    source_file=str(filepath.name),
                    chunk_index=page_num,
                    file_type="pdf",
                )
            )

    doc.close()
    return chunks


def parse_pdf(filepath: Path) -> List[DocumentChunk]:
    """Two-pass PDF parsing with fallback."""
    chunks = []

    try:
        doc = fitz.open(filepath)
        toc = doc.get_toc()

        # Try to extract title from metadata or first page
        title = doc.metadata.get("title") or filepath.stem.replace("-", " ").replace("_", " ")

        for page_num, page in enumerate(doc):
            text = page.get_text("text")

            section = detect_section_header(page, toc, page_num)
            has_figures = len(page.get_images()) > 0

            tables = extract_tables_pdfplumber(filepath, page_num)
            has_tables = len(tables) > 0

            if tables:
                text += "\n\n[Tables on this page:]\n"
                for table in tables:
                    text += format_table(table) + "\n"

            if text.strip():
                # Add contextual prefix
                context = f"Policy Document: {title}\nPage: {page_num + 1}"
                if section:
                    context += f"\nSection: {section}"
                context += "\n\n"

                chunks.append(
                    DocumentChunk(
                        content=context + text.strip(),
                        page_number=page_num + 1,
                        section_header=section,
                        has_tables=has_tables,
                        has_figures=has_figures,
                        source_file=str(filepath.name),
                        chunk_index=page_num,
                        document_title=title,
                        file_type="pdf",
                    )
                )

        doc.close()

    except Exception as e:
        logger.warning(f"Structured parsing failed for {filepath}, falling back to raw: {e}")
        chunks = fallback_raw_extraction(filepath)

    return chunks


def parse_docx(filepath: Path) -> List[DocumentChunk]:
    """Parse DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not installed, cannot parse DOCX files")
        return []

    try:
        doc = Document(filepath)
        title = filepath.stem.replace("-", " ").replace("_", " ")

        # Extract all text from paragraphs
        full_text = []
        current_section = None
        section_texts = []
        chunks = []
        chunk_index = 0

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Check if this is a heading
            if para.style and para.style.name.startswith("Heading"):
                # Save previous section if exists
                if section_texts:
                    context = f"Policy Document: {title}"
                    if current_section:
                        context += f"\nSection: {current_section}"
                    context += "\n\n"

                    chunks.append(
                        DocumentChunk(
                            content=context + "\n".join(section_texts),
                            page_number=None,  # DOCX doesn't have clear page numbers
                            section_header=current_section,
                            has_tables=False,
                            has_figures=False,
                            source_file=str(filepath.name),
                            chunk_index=chunk_index,
                            document_title=title,
                            file_type="docx",
                        )
                    )
                    chunk_index += 1
                    section_texts = []

                current_section = text
            else:
                section_texts.append(text)

        # Don't forget the last section
        if section_texts:
            context = f"Policy Document: {title}"
            if current_section:
                context += f"\nSection: {current_section}"
            context += "\n\n"

            chunks.append(
                DocumentChunk(
                    content=context + "\n".join(section_texts),
                    page_number=None,
                    section_header=current_section,
                    has_tables=False,
                    has_figures=False,
                    source_file=str(filepath.name),
                    chunk_index=chunk_index,
                    document_title=title,
                    file_type="docx",
                )
            )

        return chunks

    except Exception as e:
        logger.error(f"Failed to parse DOCX {filepath}: {e}")
        return []


def parse_document(filepath: Path) -> List[DocumentChunk]:
    """Parse a document (PDF or DOCX) and return chunks."""
    suffix = filepath.suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(filepath)
    elif suffix == ".docx":
        return parse_docx(filepath)
    else:
        logger.warning(f"Unsupported file type: {suffix}")
        return []


def parse_document_directory(directory: Path) -> List[DocumentChunk]:
    """Parse all PDF and DOCX files in a directory."""
    if not directory.exists():
        return []

    chunks = []
    files = list(directory.glob("*.pdf")) + list(directory.glob("*.docx"))

    for filepath in files:
        try:
            file_chunks = parse_document(filepath)
            chunks.extend(file_chunks)
        except Exception as e:
            logger.error(f"Failed to parse {filepath}: {e}")

    return chunks
