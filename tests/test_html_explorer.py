"""Tests for Python HTML explorer templating."""

from aion.tools.html_explorer import generate_explorer_html

_MINIMAL_YAML = """
type: architecture_notes
meta:
  repo_name: test-repo
  branch: main
summary:
  repo_name: test-repo
  structure_type: library
  tech_stack: [Python]
  total_components: 2
  total_files_analyzed: 5
  total_edges: 1
components:
  - id: mod:core
    name: core
    type: service
    path: src/core
    source: code_analysis
    role: api
    language: Python
    key_classes:
      - name: App
        bases: []
        methods: [run, stop]
        collaborators: []
  - id: mod:weaviate
    name: weaviate
    type: service
    path: cr.weaviate.io/semitechnologies/weaviate
    source: docker-compose
    role: vector_db
    language: null
    key_classes: []
edges:
  - from: mod:core
    to: mod:weaviate
    relation: api_call
    evidence: "import: weaviate in src/core/db.py"
deployment:
  containerized: true
  orchestration: docker-compose
"""


class TestGenerateExplorerHtml:

    def test_returns_valid_html(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_repo_name_in_title(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert "test-repo" in html
        assert "<title>" in html

    def test_weaviate_classified_as_infrastructure(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert '"infra"' in html
        assert "weaviate" in html

    def test_core_classified_as_core_services(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert '"core"' in html

    def test_all_components_present_in_data(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert '"core"' in html
        assert '"weaviate"' in html

    def test_edges_present_in_data(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert "api_call" in html
        assert "weaviate in src/core/db.py" in html

    def test_export_button_label(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert "Export JSON" in html

    def test_no_archimate_references_in_output(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert "ArchiMate" not in html

    def test_class_methods_present(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert '"run"' in html or "'run'" in html
        assert '"stop"' in html or "'stop'" in html

    def test_invalid_yaml_returns_none(self):
        result = generate_explorer_html("not: valid: yaml: [")
        assert result is None

    def test_empty_components_returns_html(self):
        minimal = """
type: architecture_notes
meta: { repo_name: empty }
summary: { total_components: 0 }
components: []
edges: []
"""
        html = generate_explorer_html(minimal)
        assert html is not None
        assert "<!DOCTYPE html>" in html

    def test_mod_prefix_stripped_from_edges(self):
        """Edges with mod: prefix must be normalized to bare names."""
        html = generate_explorer_html(_MINIMAL_YAML)
        assert '"from": "mod:' not in html
        assert '"to": "mod:' not in html

    def test_tier_priority_agent_before_support(self):
        """agent-monitor should classify as Agents (rule 2), not Support (rule 4)."""
        yaml_str = """
type: architecture_notes
meta: { repo_name: test }
summary: { total_components: 1 }
components:
  - id: mod:agent-monitor
    name: agent-monitor
    type: service
    path: src/agent-monitor
    source: code_analysis
    role: monitoring
    language: Python
    key_classes: []
edges: []
"""
        html = generate_explorer_html(yaml_str)
        assert '"agent"' in html

    def test_html_contains_js_functions(self):
        html = generate_explorer_html(_MINIMAL_YAML)
        assert "const DATA =" in html
        assert "const TIERS =" in html
        assert "renderExplorer()" in html
        assert "exportJSON" in html

    def test_missing_optional_fields_no_crash(self):
        """Minimal YAML with just component names."""
        yaml_str = """
components:
  - name: foo
edges: []
"""
        html = generate_explorer_html(yaml_str)
        assert html is not None
        assert "foo" in html

    def test_infra_keyword_substring_match(self):
        """postgres-connector should classify as Infrastructure via substring."""
        yaml_str = """
components:
  - name: postgres-connector
    source: code_analysis
edges: []
"""
        html = generate_explorer_html(yaml_str)
        assert '"infra"' in html

    def test_no_edges_key_still_produces_html(self):
        yaml_str = """
type: architecture_notes
meta: { repo_name: no-edges }
summary: { total_components: 1 }
components:
  - name: solo
    type: service
    source: code_analysis
"""
        html = generate_explorer_html(yaml_str)
        assert html is not None
        assert "solo" in html
