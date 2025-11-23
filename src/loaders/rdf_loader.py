"""RDF/SKOS vocabulary loader for Weaviate ingestion."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, OWL, DC, DCTERMS

logger = logging.getLogger(__name__)

# Common namespaces used in energy sector vocabularies
IEC = Namespace("http://iec.ch/TC57/")
CIM = Namespace("http://iec.ch/TC57/CIM100#")
ESA = Namespace("https://esa.alliander.com/")


@dataclass
class SKOSConcept:
    """Represents a SKOS concept extracted from RDF."""

    uri: str
    pref_label: str
    alt_labels: list[str] = field(default_factory=list)
    definition: str = ""
    broader: list[str] = field(default_factory=list)
    narrower: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    in_scheme: str = ""
    notation: str = ""
    source_file: str = ""
    vocabulary_name: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        return {
            "uri": self.uri,
            "pref_label": self.pref_label,
            "alt_labels": self.alt_labels,
            "definition": self.definition,
            "broader": self.broader,
            "narrower": self.narrower,
            "related": self.related,
            "in_scheme": self.in_scheme,
            "notation": self.notation,
            "source_file": self.source_file,
            "vocabulary_name": self.vocabulary_name,
            # Combined text for embedding
            "content": self._build_content(),
        }

    def _build_content(self) -> str:
        """Build searchable content from concept properties."""
        parts = [f"Concept: {self.pref_label}"]
        if self.alt_labels:
            parts.append(f"Also known as: {', '.join(self.alt_labels)}")
        if self.definition:
            parts.append(f"Definition: {self.definition}")
        if self.notation:
            parts.append(f"Notation: {self.notation}")
        if self.vocabulary_name:
            parts.append(f"Vocabulary: {self.vocabulary_name}")
        return "\n".join(parts)


@dataclass
class OWLClass:
    """Represents an OWL class extracted from RDF."""

    uri: str
    label: str
    comment: str = ""
    subclass_of: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    source_file: str = ""
    vocabulary_name: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for Weaviate ingestion."""
        return {
            "uri": self.uri,
            "label": self.label,
            "comment": self.comment,
            "subclass_of": self.subclass_of,
            "properties": self.properties,
            "source_file": self.source_file,
            "vocabulary_name": self.vocabulary_name,
            "content": self._build_content(),
        }

    def _build_content(self) -> str:
        """Build searchable content from class properties."""
        parts = [f"Class: {self.label}"]
        if self.comment:
            parts.append(f"Description: {self.comment}")
        if self.subclass_of:
            parts.append(f"Parent classes: {', '.join(self.subclass_of)}")
        if self.vocabulary_name:
            parts.append(f"Ontology: {self.vocabulary_name}")
        return "\n".join(parts)


class RDFLoader:
    """Loader for RDF/SKOS/OWL vocabulary files."""

    def __init__(self, rdf_path: Path):
        """Initialize the RDF loader.

        Args:
            rdf_path: Path to directory containing RDF files
        """
        self.rdf_path = Path(rdf_path)

    def load_all(self) -> Iterator[dict]:
        """Load all RDF files and yield concepts/classes.

        Yields:
            Dictionary representations of SKOS concepts and OWL classes
        """
        ttl_files = list(self.rdf_path.glob("*.ttl"))
        logger.info(f"Found {len(ttl_files)} TTL files to process")

        for ttl_file in ttl_files:
            try:
                yield from self._load_file(ttl_file)
            except Exception as e:
                logger.error(f"Error loading {ttl_file}: {e}")
                continue

    def _load_file(self, file_path: Path) -> Iterator[dict]:
        """Load a single RDF file.

        Args:
            file_path: Path to the TTL file

        Yields:
            Dictionary representations of concepts/classes
        """
        logger.info(f"Loading RDF file: {file_path.name}")
        graph = Graph()
        graph.parse(file_path, format="turtle")

        vocabulary_name = file_path.stem

        # Extract SKOS concepts
        concept_count = 0
        for concept in self._extract_skos_concepts(graph, file_path, vocabulary_name):
            concept_count += 1
            yield concept.to_dict()

        # Extract OWL classes
        class_count = 0
        for owl_class in self._extract_owl_classes(graph, file_path, vocabulary_name):
            class_count += 1
            yield owl_class.to_dict()

        logger.info(
            f"Extracted {concept_count} concepts and {class_count} classes from {file_path.name}"
        )

    def _extract_skos_concepts(
        self, graph: Graph, file_path: Path, vocabulary_name: str
    ) -> Iterator[SKOSConcept]:
        """Extract SKOS concepts from a graph.

        Args:
            graph: RDFLib graph
            file_path: Source file path
            vocabulary_name: Name of the vocabulary

        Yields:
            SKOSConcept objects
        """
        for concept_uri in graph.subjects(RDF.type, SKOS.Concept):
            concept = SKOSConcept(
                uri=str(concept_uri),
                pref_label=self._get_label(graph, concept_uri, SKOS.prefLabel),
                alt_labels=self._get_labels(graph, concept_uri, SKOS.altLabel),
                definition=self._get_literal(graph, concept_uri, SKOS.definition),
                broader=self._get_related_uris(graph, concept_uri, SKOS.broader),
                narrower=self._get_related_uris(graph, concept_uri, SKOS.narrower),
                related=self._get_related_uris(graph, concept_uri, SKOS.related),
                in_scheme=self._get_first_uri(graph, concept_uri, SKOS.inScheme),
                notation=self._get_literal(graph, concept_uri, SKOS.notation),
                source_file=file_path.name,
                vocabulary_name=vocabulary_name,
            )

            # Skip concepts without labels
            if concept.pref_label:
                yield concept

    def _extract_owl_classes(
        self, graph: Graph, file_path: Path, vocabulary_name: str
    ) -> Iterator[OWLClass]:
        """Extract OWL classes from a graph.

        Args:
            graph: RDFLib graph
            file_path: Source file path
            vocabulary_name: Name of the vocabulary

        Yields:
            OWLClass objects
        """
        for class_uri in graph.subjects(RDF.type, OWL.Class):
            owl_class = OWLClass(
                uri=str(class_uri),
                label=self._get_label(graph, class_uri, RDFS.label),
                comment=self._get_literal(graph, class_uri, RDFS.comment),
                subclass_of=self._get_related_uris(graph, class_uri, RDFS.subClassOf),
                source_file=file_path.name,
                vocabulary_name=vocabulary_name,
            )

            # Use local name if no label
            if not owl_class.label and isinstance(class_uri, URIRef):
                owl_class.label = self._get_local_name(class_uri)

            if owl_class.label:
                yield owl_class

    def _get_label(self, graph: Graph, subject: URIRef, predicate) -> str:
        """Get a single label, preferring English."""
        labels = list(graph.objects(subject, predicate))
        if not labels:
            return ""

        # Prefer English labels
        for label in labels:
            if hasattr(label, "language") and label.language in ("en", "en-US"):
                return str(label)

        return str(labels[0])

    def _get_labels(self, graph: Graph, subject: URIRef, predicate) -> list[str]:
        """Get all labels for a predicate."""
        return [str(obj) for obj in graph.objects(subject, predicate)]

    def _get_literal(self, graph: Graph, subject: URIRef, predicate) -> str:
        """Get a single literal value."""
        for obj in graph.objects(subject, predicate):
            return str(obj)
        return ""

    def _get_related_uris(
        self, graph: Graph, subject: URIRef, predicate
    ) -> list[str]:
        """Get list of related URIs."""
        return [str(obj) for obj in graph.objects(subject, predicate)]

    def _get_first_uri(self, graph: Graph, subject: URIRef, predicate) -> str:
        """Get first URI for a predicate."""
        for obj in graph.objects(subject, predicate):
            return str(obj)
        return ""

    def _get_local_name(self, uri: URIRef) -> str:
        """Extract local name from URI."""
        uri_str = str(uri)
        if "#" in uri_str:
            return uri_str.split("#")[-1]
        return uri_str.split("/")[-1]
