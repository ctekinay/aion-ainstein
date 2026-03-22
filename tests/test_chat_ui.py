"""Tests for chat_ui helper functions."""


from aion.chat_ui import _query_references_artifact


class TestQueryReferencesArtifact:
    """Tests for _query_references_artifact() — content-type-aware artifact detection."""

    # --- Intent gating ---

    def test_rejects_identity_intent(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("tell me about the model", "identity", artifact) is False

    def test_rejects_generation_intent(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("generate a model", "generation", artifact) is False

    def test_rejects_off_topic_intent(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("what about this model", "off_topic", artifact) is False

    # --- ArchiMate artifact + follow_up ---

    def test_archimate_follow_up_with_model(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("compare this model to the principles", "follow_up", artifact) is True

    def test_archimate_follow_up_with_archimate(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("how does this archimate align with ADR.29?", "follow_up", artifact) is True

    def test_archimate_follow_up_with_element(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("what elements are missing?", "follow_up", artifact) is True

    def test_archimate_follow_up_with_relationship(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("show the relationship types", "follow_up", artifact) is True

    def test_archimate_follow_up_with_artifact(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("analyze this artifact", "follow_up", artifact) is True

    def test_archimate_follow_up_no_keywords_recent(self):
        """Recent artifact (<=4 turns) is injected for follow_up even without keywords."""
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("what ADRs exist?", "follow_up", artifact, artifact_age=2) is True

    def test_archimate_follow_up_no_keywords_stale(self):
        """Stale artifact (>4 turns) is NOT injected without explicit keywords."""
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("what ADRs exist?", "follow_up", artifact, artifact_age=10) is False

    # --- ArchiMate artifact + retrieval ---

    def test_archimate_retrieval_with_model(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("compare model to principles", "retrieval", artifact) is True

    def test_archimate_retrieval_no_keywords(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("list all principles", "retrieval", artifact) is False

    # --- YAML artifact ---

    def test_yaml_artifact_with_model(self):
        artifact = {"content_type": "text/yaml"}
        assert _query_references_artifact("refine this model", "follow_up", artifact) is True

    def test_yaml_artifact_no_keywords_recent(self):
        """Recent YAML artifact injected for follow_up without keywords."""
        artifact = {"content_type": "text/yaml"}
        assert _query_references_artifact("what ADRs exist?", "follow_up", artifact, artifact_age=2) is True

    def test_yaml_artifact_no_keywords_stale(self):
        """Stale YAML artifact NOT injected without keywords."""
        artifact = {"content_type": "text/yaml"}
        assert _query_references_artifact("what ADRs exist?", "follow_up", artifact, artifact_age=10) is False

    # --- Generic artifact ---

    def test_generic_artifact_with_keyword(self):
        artifact = {"content_type": "text/plain"}
        assert _query_references_artifact("analyze the artifact", "follow_up", artifact) is True

    def test_generic_artifact_without_keyword(self):
        artifact = {"content_type": "text/plain"}
        assert _query_references_artifact("what is this document about?", "follow_up", artifact) is False

    # --- Edge cases ---

    def test_case_insensitive(self):
        artifact = {"content_type": "archimate/xml"}
        assert _query_references_artifact("Compare this MODEL to ADR.29", "follow_up", artifact) is True

    def test_empty_content_type(self):
        artifact = {"content_type": ""}
        assert _query_references_artifact("analyze the artifact", "follow_up", artifact) is True

    def test_missing_content_type(self):
        artifact = {}
        assert _query_references_artifact("analyze the artifact", "follow_up", artifact) is True
