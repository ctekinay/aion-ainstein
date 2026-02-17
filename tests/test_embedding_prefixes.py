"""Tests for nomic-embed-text-v2 search_document/search_query prefixes.

Validates that:
- embed_query() prepends "search_query: " to the input
- embed_documents() prepends "search_document: " to each input
- embed_text() and embed_texts() remain raw (no prefix) — used by classifier
- Classifier centroid build and classify stay in unprefixed space
"""

from unittest.mock import patch, MagicMock

import pytest


FAKE_VECTOR = [0.1] * 768


@pytest.fixture(autouse=True)
def _reset_global_client():
    """Reset the global embeddings client between tests."""
    import src.weaviate.embeddings as mod
    old = mod._embeddings_client
    mod._embeddings_client = None
    yield
    mod._embeddings_client = old


@pytest.fixture
def mock_ollama():
    """Patch OllamaEmbeddings to capture inputs without hitting Ollama."""
    with patch("src.weaviate.embeddings.OllamaEmbeddings") as MockCls:
        instance = MagicMock()
        instance.embed = MagicMock(return_value=FAKE_VECTOR)
        instance.embed_batch = MagicMock(
            side_effect=lambda texts: [FAKE_VECTOR] * len(texts)
        )
        MockCls.return_value = instance
        yield instance


# ── embed_query: prepends search_query: prefix ────────────────────────

class TestEmbedQuery:
    def test_prepends_search_query_prefix(self, mock_ollama):
        from src.weaviate.embeddings import embed_query

        embed_query("What does ADR.12 decide?")
        mock_ollama.embed.assert_called_once_with("search_query: What does ADR.12 decide?")

    def test_returns_embedding_vector(self, mock_ollama):
        from src.weaviate.embeddings import embed_query

        result = embed_query("hello")
        assert result == FAKE_VECTOR

    def test_empty_string_still_prefixed(self, mock_ollama):
        from src.weaviate.embeddings import embed_query

        embed_query("")
        mock_ollama.embed.assert_called_once_with("search_query: ")


# ── embed_documents: prepends search_document: prefix ─────────────────

class TestEmbedDocuments:
    def test_prepends_search_document_prefix(self, mock_ollama):
        from src.weaviate.embeddings import embed_documents

        embed_documents(["ADR.12 full text", "PCP.22 full text"])
        mock_ollama.embed_batch.assert_called_once_with(
            ["search_document: ADR.12 full text", "search_document: PCP.22 full text"]
        )

    def test_returns_list_of_vectors(self, mock_ollama):
        from src.weaviate.embeddings import embed_documents

        result = embed_documents(["a", "b", "c"])
        assert len(result) == 3
        assert all(v == FAKE_VECTOR for v in result)

    def test_empty_list(self, mock_ollama):
        from src.weaviate.embeddings import embed_documents

        result = embed_documents([])
        mock_ollama.embed_batch.assert_called_once_with([])


# ── embed_text / embed_texts: stay raw (no prefix) ────────────────────

class TestRawEmbedding:
    def test_embed_text_no_prefix(self, mock_ollama):
        from src.weaviate.embeddings import embed_text

        embed_text("hello world")
        mock_ollama.embed.assert_called_once_with("hello world")

    def test_embed_texts_no_prefix(self, mock_ollama):
        from src.weaviate.embeddings import embed_texts

        embed_texts(["foo", "bar"])
        mock_ollama.embed_batch.assert_called_once_with(["foo", "bar"])


# ── Classifier uses raw functions (no prefix leakage) ─────────────────

class TestClassifierNoPrefixLeakage:
    def test_create_classifier_uses_raw_embed(self, mock_ollama):
        """create_classifier passes embed_text/embed_texts, not prefixed versions."""
        from src.weaviate.embeddings import embed_text, embed_texts

        with patch("src.agents.architecture_agent.EmbeddingClassifier") as MockCls, \
             patch("src.config.settings") as mock_settings:
            mock_settings.get_routing_policy.return_value = {
                "embedding_classifier_enabled": True,
            }
            mock_settings.resolve_path.return_value = "/fake/path.yaml"
            MockCls.return_value = MagicMock()

            from src.agents.architecture_agent import create_classifier
            create_classifier()

            # Verify the exact function references passed (raw, not prefixed)
            call_kwargs = MockCls.call_args
            assert call_kwargs[1]["embed_fn"] is embed_text
            assert call_kwargs[1]["embed_batch_fn"] is embed_texts
