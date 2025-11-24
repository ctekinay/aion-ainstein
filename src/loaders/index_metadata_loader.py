"""Loader for index.md metadata files that describe document collections.

Each directory containing documents can have an index.md file that provides
metadata about the ownership and context of the documents within.

Example index.md format:
```markdown
---
# Ownership Information (applies to all documents in this directory)
ownership:
  team:
    en: Energy System Architecture
    nl: Energie Systeem Architectuur
  team_abbr:
    en: ESA
    nl: ESA
  department:
    en: System Operations
    nl: Systeem Operaties
  department_abbr:
    en: SO
    nl: SO
  organization:
    en: Alliander
    nl: Alliander

# Document Collection Information
collection:
  name:
    en: Architecture Decision Records
    nl: Architectuur Besluit Records
  description:
    en: Architectural decisions for the energy system
    nl: Architectuurbeslissingen voor het energiesysteem
  doc_types:
    - adr
    - principle
  keywords:
    en: [architecture, decisions, standards, protocols]
    nl: [architectuur, besluiten, standaarden, protocollen]

# Individual Document Metadata
documents:
  - file_name: "ADR-001-use-cim-standards.md"
    title:
      en: "Use CIM Standards as Domain Language"
      nl: "Gebruik CIM Standaarden als Domein Taal"
    description:
      en: "Decision to adopt IEC CIM standards for semantic interoperability"
      nl: "Besluit om IEC CIM standaarden te gebruiken voor semantische interoperabiliteit"
    format: markdown
    doc_type: adr
    status: accepted
    version: "1.0"
    created_date: "2024-01-15"
    modified_date: "2024-03-20"
    created_by: "John Doe"
    modified_by: "Jane Smith"
    tags: [cim, iec, standards, interoperability]

  - file_name: "ADR-002-oauth-authentication.md"
    title:
      en: "OAuth 2.0 for Authentication"
      nl: "OAuth 2.0 voor Authenticatie"
    format: markdown
    doc_type: adr
    status: accepted
    version: "1.2"
    created_date: "2024-02-01"
    modified_date: "2024-06-15"
    created_by: "Jane Smith"
    tags: [security, authentication, oauth]
---

# Energy System Architecture Documents

This directory contains architectural decision records and principles
for the Energy System Architecture team.
```
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LocalizedText:
    """Text with English and Dutch versions."""
    en: str = ""
    nl: str = ""

    def __str__(self) -> str:
        return self.en or self.nl or ""

    def to_dict(self) -> dict:
        return {"en": self.en, "nl": self.nl}


@dataclass
class OwnershipInfo:
    """Ownership information for a document collection."""
    team: LocalizedText = field(default_factory=LocalizedText)
    team_abbr: LocalizedText = field(default_factory=LocalizedText)
    department: LocalizedText = field(default_factory=LocalizedText)
    department_abbr: LocalizedText = field(default_factory=LocalizedText)
    organization: LocalizedText = field(default_factory=LocalizedText)

    def to_dict(self) -> dict:
        return {
            "team": self.team.to_dict(),
            "team_abbr": self.team_abbr.to_dict(),
            "department": self.department.to_dict(),
            "department_abbr": self.department_abbr.to_dict(),
            "organization": self.organization.to_dict(),
        }

    def get_display_name(self, lang: str = "en") -> str:
        """Get a display name for the ownership."""
        if lang == "nl":
            team = self.team.nl or self.team_abbr.nl or ""
            dept = self.department.nl or self.department_abbr.nl or ""
            org = self.organization.nl or ""
        else:
            team = self.team.en or self.team_abbr.en or ""
            dept = self.department.en or self.department_abbr.en or ""
            org = self.organization.en or ""

        parts = [p for p in [org, dept, team] if p]
        return " / ".join(parts) if parts else "Unknown"


@dataclass
class CollectionInfo:
    """Information about a document collection."""
    name: LocalizedText = field(default_factory=LocalizedText)
    description: LocalizedText = field(default_factory=LocalizedText)
    doc_types: list[str] = field(default_factory=list)
    keywords_en: list[str] = field(default_factory=list)
    keywords_nl: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name.to_dict(),
            "description": self.description.to_dict(),
            "doc_types": self.doc_types,
            "keywords_en": self.keywords_en,
            "keywords_nl": self.keywords_nl,
        }


@dataclass
class DocumentInfo:
    """Metadata for an individual document."""
    file_name: str = ""
    full_path: str = ""
    title: LocalizedText = field(default_factory=LocalizedText)
    description: LocalizedText = field(default_factory=LocalizedText)
    format: str = ""  # markdown, pdf, docx, etc.
    doc_type: str = ""  # adr, principle, policy, etc.
    status: str = ""  # draft, accepted, deprecated, etc.
    version: str = ""
    created_date: str = ""
    modified_date: str = ""
    created_by: str = ""
    modified_by: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "full_path": self.full_path,
            "title": self.title.to_dict(),
            "description": self.description.to_dict(),
            "format": self.format,
            "doc_type": self.doc_type,
            "status": self.status,
            "version": self.version,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
            "created_by": self.created_by,
            "modified_by": self.modified_by,
            "tags": self.tags,
        }

    def get_flat_metadata(self) -> dict:
        """Get flattened metadata for document properties."""
        return {
            "doc_title": self.title.en or self.title.nl,
            "doc_title_nl": self.title.nl,
            "doc_description": self.description.en or self.description.nl,
            "doc_format": self.format,
            "doc_type": self.doc_type,
            "doc_status": self.status,
            "doc_version": self.version,
            "doc_created_date": self.created_date,
            "doc_modified_date": self.modified_date,
            "doc_created_by": self.created_by,
            "doc_modified_by": self.modified_by,
            "doc_tags": self.tags,
        }


@dataclass
class IndexMetadata:
    """Complete metadata from an index.md file."""
    source_path: str = ""
    ownership: OwnershipInfo = field(default_factory=OwnershipInfo)
    collection: CollectionInfo = field(default_factory=CollectionInfo)
    documents: list[DocumentInfo] = field(default_factory=list)
    raw_content: str = ""

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "ownership": self.ownership.to_dict(),
            "collection": self.collection.to_dict(),
            "documents": [d.to_dict() for d in self.documents],
        }

    def get_flat_metadata(self) -> dict:
        """Get flattened ownership/collection metadata for document properties."""
        return {
            "owner_team": self.ownership.team.en or self.ownership.team_abbr.en,
            "owner_team_abbr": self.ownership.team_abbr.en,
            "owner_team_nl": self.ownership.team.nl or self.ownership.team_abbr.nl,
            "owner_department": self.ownership.department.en or self.ownership.department_abbr.en,
            "owner_department_abbr": self.ownership.department_abbr.en,
            "owner_organization": self.ownership.organization.en,
            "owner_display": self.ownership.get_display_name("en"),
            "owner_display_nl": self.ownership.get_display_name("nl"),
            "collection_name": self.collection.name.en,
            "collection_description": self.collection.description.en,
            "keywords": self.collection.keywords_en,
        }

    def get_document_by_filename(self, filename: str) -> Optional[DocumentInfo]:
        """Find document metadata by filename."""
        for doc in self.documents:
            if doc.file_name == filename:
                return doc
        return None

    def get_combined_metadata(self, filename: str) -> dict:
        """Get combined ownership + document metadata for a specific file."""
        result = self.get_flat_metadata()
        doc = self.get_document_by_filename(filename)
        if doc:
            result.update(doc.get_flat_metadata())
        return result


def _parse_localized(data: dict | str | None) -> LocalizedText:
    """Parse a localized text field."""
    if data is None:
        return LocalizedText()
    if isinstance(data, str):
        return LocalizedText(en=data, nl=data)
    return LocalizedText(
        en=data.get("en", ""),
        nl=data.get("nl", ""),
    )


def _parse_ownership(data: dict | None) -> OwnershipInfo:
    """Parse ownership information from YAML data."""
    if not data:
        return OwnershipInfo()

    return OwnershipInfo(
        team=_parse_localized(data.get("team")),
        team_abbr=_parse_localized(data.get("team_abbr")),
        department=_parse_localized(data.get("department")),
        department_abbr=_parse_localized(data.get("department_abbr")),
        organization=_parse_localized(data.get("organization")),
    )


def _parse_collection(data: dict | None) -> CollectionInfo:
    """Parse collection information from YAML data."""
    if not data:
        return CollectionInfo()

    keywords = data.get("keywords", {})
    keywords_en = keywords.get("en", []) if isinstance(keywords, dict) else []
    keywords_nl = keywords.get("nl", []) if isinstance(keywords, dict) else []

    return CollectionInfo(
        name=_parse_localized(data.get("name")),
        description=_parse_localized(data.get("description")),
        doc_types=data.get("doc_types", []),
        keywords_en=keywords_en,
        keywords_nl=keywords_nl,
    )


def _parse_document(data: dict, base_path: Path) -> DocumentInfo:
    """Parse individual document metadata from YAML data."""
    file_name = data.get("file_name", "")
    full_path = str(base_path / file_name) if file_name else ""

    return DocumentInfo(
        file_name=file_name,
        full_path=full_path,
        title=_parse_localized(data.get("title")),
        description=_parse_localized(data.get("description")),
        format=data.get("format", ""),
        doc_type=data.get("doc_type", ""),
        status=data.get("status", ""),
        version=str(data.get("version", "")),
        created_date=str(data.get("created_date", "")),
        modified_date=str(data.get("modified_date", "")),
        created_by=data.get("created_by", ""),
        modified_by=data.get("modified_by", ""),
        tags=data.get("tags", []),
    )


def _parse_documents(data: list | None, base_path: Path) -> list[DocumentInfo]:
    """Parse list of document metadata from YAML data."""
    if not data:
        return []

    return [_parse_document(doc, base_path) for doc in data if isinstance(doc, dict)]


def load_index_metadata(index_path: Path) -> Optional[IndexMetadata]:
    """Load and parse an index.md file.

    Args:
        index_path: Path to the index.md file

    Returns:
        IndexMetadata object or None if file doesn't exist or can't be parsed
    """
    if not index_path.exists():
        logger.debug(f"No index.md found at {index_path}")
        return None

    try:
        content = index_path.read_text(encoding="utf-8")

        # Extract YAML frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not frontmatter_match:
            logger.warning(f"No YAML frontmatter found in {index_path}")
            return None

        yaml_content = frontmatter_match.group(1)
        data = yaml.safe_load(yaml_content)

        if not data:
            logger.warning(f"Empty YAML frontmatter in {index_path}")
            return None

        # Base path for resolving document paths
        base_path = index_path.parent

        return IndexMetadata(
            source_path=str(index_path),
            ownership=_parse_ownership(data.get("ownership")),
            collection=_parse_collection(data.get("collection")),
            documents=_parse_documents(data.get("documents"), base_path),
            raw_content=content,
        )

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML in {index_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load index.md from {index_path}: {e}")
        return None


def find_index_metadata(file_path: Path) -> Optional[IndexMetadata]:
    """Find and load index.md metadata for a file.

    Searches for index.md in the file's directory and parent directories
    until it finds one or reaches the data root.

    Args:
        file_path: Path to a document file

    Returns:
        IndexMetadata from the nearest index.md, or None if not found
    """
    current_dir = file_path.parent if file_path.is_file() else file_path

    # Search up to 5 levels up for index.md
    for _ in range(5):
        index_path = current_dir / "index.md"
        metadata = load_index_metadata(index_path)
        if metadata:
            return metadata

        # Stop at 'data' directory
        if current_dir.name == "data":
            break

        parent = current_dir.parent
        if parent == current_dir:
            break
        current_dir = parent

    return None


class IndexMetadataCache:
    """Cache for index.md metadata to avoid repeated file reads."""

    def __init__(self):
        self._cache: dict[str, Optional[IndexMetadata]] = {}

    def get_metadata(self, file_path: Path) -> Optional[IndexMetadata]:
        """Get metadata for a file, using cache when possible."""
        dir_path = file_path.parent if file_path.is_file() else file_path
        cache_key = str(dir_path)

        if cache_key not in self._cache:
            self._cache[cache_key] = find_index_metadata(file_path)

        return self._cache[cache_key]

    def clear(self):
        """Clear the cache."""
        self._cache.clear()


# Global cache instance
_metadata_cache = IndexMetadataCache()


# ===== Centralized Catalog Support =====

@dataclass
class CatalogDocument:
    """Document entry from centralized catalog."""
    id: str
    title: str
    type: str
    doc_number: str
    owner_team: str
    owner_team_abbr: str
    owner_department: str
    owner_organization: str
    source_type: str
    source_location: str
    status: str = ""
    tags: list[str] = field(default_factory=list)

    def get_owner_display(self) -> str:
        """Get display name for the owner."""
        parts = []
        if self.owner_organization:
            parts.append(self.owner_organization)
        if self.owner_department:
            parts.append(self.owner_department)
        if self.owner_team:
            parts.append(self.owner_team)
        return " / ".join(parts) if parts else "Unknown"

    def to_flat_metadata(self) -> dict:
        """Convert to flat metadata dictionary."""
        return {
            "doc_id": self.id,
            "doc_number": self.doc_number,
            "title": self.title,
            "doc_type": self.type,
            "status": self.status,
            "owner_team": self.owner_team,
            "owner_team_abbr": self.owner_team_abbr,
            "owner_department": self.owner_department,
            "owner_organization": self.owner_organization,
            "owner_display": self.get_owner_display(),
            "collection_name": f"{self.owner_team_abbr} {self.type.upper()}s" if self.owner_team_abbr else "",
            "source_location": self.source_location,
            "tags": self.tags,
        }


class CentralizedCatalog:
    """Centralized document catalog loaded from data/index.md"""

    def __init__(self, catalog_path: Path):
        """Initialize catalog from file.

        Args:
            catalog_path: Path to the centralized index.md file
        """
        self.catalog_path = catalog_path
        self.documents: dict[str, CatalogDocument] = {}
        self.location_map: dict[str, CatalogDocument] = {}
        self._load()

    def _load(self):
        """Load catalog from file."""
        if not self.catalog_path.exists():
            logger.warning(f"Centralized catalog not found at {self.catalog_path}")
            return

        try:
            content = self.catalog_path.read_text(encoding="utf-8")

            # Extract YAML frontmatter
            frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if not frontmatter_match:
                logger.warning(f"No YAML frontmatter in centralized catalog")
                return

            yaml_content = frontmatter_match.group(1)
            data = yaml.safe_load(yaml_content)

            if not data or "documents" not in data:
                logger.warning("No documents found in centralized catalog")
                return

            # Parse document entries
            for doc_data in data["documents"]:
                try:
                    owner = doc_data.get("owner", {})
                    source = doc_data.get("source", {})

                    doc = CatalogDocument(
                        id=doc_data.get("id", ""),
                        title=doc_data.get("title", ""),
                        type=doc_data.get("type", ""),
                        doc_number=doc_data.get("doc_number", ""),
                        owner_team=owner.get("team", ""),
                        owner_team_abbr=owner.get("team_abbr", ""),
                        owner_department=owner.get("department", ""),
                        owner_organization=owner.get("organization", ""),
                        source_type=source.get("type", ""),
                        source_location=source.get("location", ""),
                        status=doc_data.get("status", ""),
                        tags=doc_data.get("tags", []),
                    )

                    self.documents[doc.id] = doc
                    if doc.source_location:
                        self.location_map[doc.source_location] = doc

                except Exception as e:
                    logger.error(f"Failed to parse document entry: {e}")
                    continue

            logger.info(f"Loaded {len(self.documents)} documents from centralized catalog")

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in centralized catalog: {e}")
        except Exception as e:
            logger.error(f"Failed to load centralized catalog: {e}")

    def get_by_id(self, doc_id: str) -> Optional[CatalogDocument]:
        """Get document by ID."""
        return self.documents.get(doc_id)

    def get_by_location(self, location: str) -> Optional[CatalogDocument]:
        """Get document by source location (file path)."""
        return self.location_map.get(location)

    def get_by_owner(self, owner_abbr: str) -> list[CatalogDocument]:
        """Get all documents owned by a specific team."""
        return [
            doc for doc in self.documents.values()
            if doc.owner_team_abbr.lower() == owner_abbr.lower()
        ]

    def get_by_type(self, doc_type: str) -> list[CatalogDocument]:
        """Get all documents of a specific type."""
        return [
            doc for doc in self.documents.values()
            if doc.type.lower() == doc_type.lower()
        ]


# Global centralized catalog instance
_centralized_catalog: Optional[CentralizedCatalog] = None


def get_centralized_catalog() -> CentralizedCatalog:
    """Get or create the global centralized catalog instance."""
    global _centralized_catalog
    if _centralized_catalog is None:
        from ..config import settings
        catalog_path = settings.resolve_path(settings.base_path) / "data" / "index.md"
        _centralized_catalog = CentralizedCatalog(catalog_path)
    return _centralized_catalog


def get_document_metadata(file_path: Path) -> dict:
    """Get metadata for a document file.

    First tries to find metadata in the centralized catalog,
    then falls back to directory-based index.md files.

    Args:
        file_path: Path to the document

    Returns:
        Dictionary with ownership, collection, and document metadata
    """
    # Default values
    defaults = {
        # Ownership fields
        "doc_id": "",
        "doc_number": "",
        "owner_team": "",
        "owner_team_abbr": "",
        "owner_department": "",
        "owner_organization": "",
        "owner_display": "Unknown",
        # Collection fields
        "collection_name": "",
        "tags": [],
    }

    # Try centralized catalog first
    try:
        catalog = get_centralized_catalog()
        # Convert file path to relative path from project root
        file_path_str = str(file_path).replace("\\", "/")

        # Try different path variations
        for path_variant in [
            file_path_str,
            file_path_str.split("/data/")[-1] if "/data/" in file_path_str else "",
            f"data/{file_path_str.split('/data/')[-1]}" if "/data/" in file_path_str else "",
        ]:
            if path_variant:
                doc = catalog.get_by_location(path_variant)
                if doc:
                    result = doc.to_flat_metadata()
                    # Fill in any missing keys with defaults
                    for key, default_value in defaults.items():
                        if key not in result:
                            result[key] = default_value
                    return result
    except Exception as e:
        logger.debug(f"Centralized catalog lookup failed: {e}")

    # Fallback to directory-based index.md (legacy)
    index_metadata = _metadata_cache.get_metadata(file_path)

    if not index_metadata:
        return defaults

    # Get filename for document-specific lookup
    filename = file_path.name

    # Get combined metadata (ownership + document-specific if available)
    result = index_metadata.get_combined_metadata(filename)

    # Fill in any missing keys with defaults
    for key, default_value in defaults.items():
        if key not in result:
            result[key] = default_value

    return result
