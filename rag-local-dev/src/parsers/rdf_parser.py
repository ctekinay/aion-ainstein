"""
RDF/SKOS parser for domain terminology/ontology.
Extracts concepts with labels, definitions, and relationships.

Supports:
- Turtle (.ttl) format
- RDF/XML (.rdf, .xml) format
- N-Triples (.nt) format
"""

from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import SKOS, DCTERMS
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class SKOSConcept:
    """Represents a SKOS concept from an RDF vocabulary."""

    concept_uri: str
    pref_label_en: Optional[str]
    pref_label_nl: Optional[str]
    alt_labels: List[str]
    definition: Optional[str]
    broader_uri: Optional[str]
    narrower_uris: List[str]
    related_uris: List[str]
    in_scheme: Optional[str]
    notation: Optional[str]
    vocabulary_name: Optional[str]
    example: Optional[str] = None


def extract_vocabulary_name(filepath: Path, graph: Graph) -> str:
    """
    Extract vocabulary name from file or graph metadata.

    Looks for:
    1. dct:title on the ConceptScheme
    2. rdfs:label on the ConceptScheme
    3. Filename without extension
    """
    # Find ConceptScheme
    for scheme in graph.subjects(RDF.type, SKOS.ConceptScheme):
        # Try dct:title first
        for title in graph.objects(scheme, DCTERMS.title):
            return str(title)
        # Try rdfs:label
        for label in graph.objects(scheme, RDFS.label):
            return str(label)

    # Fallback to filename
    return filepath.stem


def parse_skos(filepath: Path) -> List[SKOSConcept]:
    """
    Parse SKOS/RDF file and extract concepts.

    Args:
        filepath: Path to the RDF file (.ttl, .rdf, .xml, .nt)

    Returns:
        List of SKOSConcept objects
    """
    g = Graph()

    # Determine format based on extension
    suffix = filepath.suffix.lower()
    format_map = {
        ".ttl": "turtle",
        ".rdf": "xml",
        ".xml": "xml",
        ".nt": "nt",
        ".n3": "n3",
    }
    rdf_format = format_map.get(suffix, "turtle")

    try:
        g.parse(filepath, format=rdf_format)
    except Exception as e:
        logger.error(f"Failed to parse RDF file {filepath}: {e}")
        return []

    vocabulary_name = extract_vocabulary_name(filepath, g)
    logger.info(f"Parsing vocabulary: {vocabulary_name}")

    concepts = []

    # Find all SKOS Concepts (and OWL Classes that are also SKOS Concepts)
    concept_uris = set()
    for concept_uri in g.subjects(RDF.type, SKOS.Concept):
        concept_uris.add(concept_uri)
    # Some files declare concepts as both owl:Class and skos:Concept
    for concept_uri in g.subjects(RDF.type, OWL.Class):
        # Check if it has SKOS properties
        if any(g.objects(concept_uri, SKOS.prefLabel)):
            concept_uris.add(concept_uri)

    for concept_uri in concept_uris:
        # Get preferred labels by language
        pref_label_en = None
        pref_label_nl = None

        for label in g.objects(concept_uri, SKOS.prefLabel):
            lang = getattr(label, "language", None)
            if lang == "en":
                pref_label_en = str(label)
            elif lang == "nl":
                pref_label_nl = str(label)
            elif lang is None and pref_label_en is None:
                # Default to English if no language tag
                pref_label_en = str(label)

        # Skip concepts without any label
        if not pref_label_en and not pref_label_nl:
            continue

        # Get alternative labels
        alt_labels = []
        for label in g.objects(concept_uri, SKOS.altLabel):
            alt_labels.append(str(label))

        # Get definition
        definition = None
        for defn in g.objects(concept_uri, SKOS.definition):
            definition = str(defn)
            # Clean up multi-line definitions
            definition = re.sub(r"\s+", " ", definition).strip()
            break

        # Get example if available
        example = None
        for ex in g.objects(concept_uri, SKOS.example):
            example = str(ex)
            break

        # Get broader concept
        broader_uri = None
        for broader in g.objects(concept_uri, SKOS.broader):
            broader_uri = str(broader)
            break

        # Get narrower concepts
        narrower_uris = [str(n) for n in g.objects(concept_uri, SKOS.narrower)]

        # Get related concepts
        related_uris = [str(r) for r in g.objects(concept_uri, SKOS.related)]

        # Get scheme
        in_scheme = None
        for scheme in g.objects(concept_uri, SKOS.inScheme):
            in_scheme = str(scheme)
            break

        # Get notation
        notation = None
        for n in g.objects(concept_uri, SKOS.notation):
            notation = str(n)
            break

        concepts.append(
            SKOSConcept(
                concept_uri=str(concept_uri),
                pref_label_en=pref_label_en,
                pref_label_nl=pref_label_nl,
                alt_labels=alt_labels,
                definition=definition,
                broader_uri=broader_uri,
                narrower_uris=narrower_uris,
                related_uris=related_uris,
                in_scheme=in_scheme,
                notation=notation,
                vocabulary_name=vocabulary_name,
                example=example,
            )
        )

    logger.info(f"Parsed {len(concepts)} SKOS concepts from {filepath}")
    return concepts


def concept_to_embedding_text(concept: SKOSConcept) -> str:
    """
    Convert SKOS concept to text for embedding.

    Creates a rich text representation that captures:
    - Labels (preferred and alternative)
    - Definition
    - Example usage
    - Vocabulary context
    """
    parts = []

    # Primary label
    if concept.pref_label_en:
        parts.append(f"Term: {concept.pref_label_en}")
    if concept.pref_label_nl and concept.pref_label_nl != concept.pref_label_en:
        parts.append(f"Dutch: {concept.pref_label_nl}")

    # Alternative labels
    if concept.alt_labels:
        parts.append(f"Also known as: {', '.join(concept.alt_labels)}")

    # Vocabulary context
    if concept.vocabulary_name:
        parts.append(f"From vocabulary: {concept.vocabulary_name}")

    # Definition
    if concept.definition:
        parts.append(f"Definition: {concept.definition}")

    # Example
    if concept.example:
        parts.append(f"Example: {concept.example}")

    return "\n".join(parts)


def parse_skos_directory(directory: Path) -> List[SKOSConcept]:
    """
    Parse all RDF/SKOS files in a directory.

    Args:
        directory: Path to directory containing RDF files

    Returns:
        List of all SKOSConcept objects from all files
    """
    if not directory.exists():
        logger.warning(f"Directory {directory} does not exist")
        return []

    all_concepts = []

    # Find all RDF files
    extensions = ["*.ttl", "*.rdf", "*.xml", "*.nt", "*.n3"]
    files = []
    for ext in extensions:
        files.extend(directory.glob(ext))

    # Filter out config files and non-vocabulary files
    files = [f for f in files if not f.name.endswith(".config") and not f.name.startswith("config")]

    logger.info(f"Found {len(files)} RDF files in {directory}")

    for filepath in files:
        try:
            concepts = parse_skos(filepath)
            all_concepts.extend(concepts)
        except Exception as e:
            logger.error(f"Failed to parse {filepath}: {e}")

    return all_concepts


def get_vocabulary_stats(concepts: List[SKOSConcept]) -> Dict[str, int]:
    """Get count of concepts per vocabulary."""
    stats = {}
    for concept in concepts:
        vocab = concept.vocabulary_name or "Unknown"
        stats[vocab] = stats.get(vocab, 0) + 1
    return stats
