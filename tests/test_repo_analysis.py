"""Tests for repository analysis tools."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from aion.tools.repo_analysis import (
    TEMPLATE_VERSION,
    _detect_modules,
    _extract_branch_from_url,
    _extract_repo_identity,
    clone_repo,
    git_diff_stats,
    merge_architecture_notes,
    profile_repo,
)
from aion.tools.repo_extractors import (
    build_dep_graph,
    extract_code_structure,
    extract_manifests,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_repo(tmp_path):
    """Create a minimal single-service repo structure."""
    (tmp_path / "README.md").write_text("# My Project\nA sample project.")
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\nsqlalchemy\npsycopg2\nredis\n")
    (tmp_path / "docker-compose.yml").write_text(
        "version: '3'\n"
        "services:\n"
        "  api:\n"
        "    build: ./src\n"
        "    ports:\n"
        "      - '8080:8080'\n"
        "    depends_on:\n"
        "      - postgres\n"
        "      - redis\n"
        "    environment:\n"
        "      DATABASE_URL: postgres://...\n"
        "      REDIS_URL: redis://...\n"
        "  postgres:\n"
        "    image: postgres:15\n"
        "    ports:\n"
        "      - '5432:5432'\n"
        "  redis:\n"
        "    image: redis:7\n"
        "networks:\n"
        "  default:\n"
        "volumes:\n"
        "  pgdata:\n"
    )
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nEXPOSE 8080\nCMD [\"uvicorn\", \"main:app\"]\n"
    )

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from .models import Order\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/orders')\n"
        "async def list_orders():\n"
        "    return []\n\n"
        "API_PREFIX = '/api/v1'\n"
    )
    models = src / "models"
    models.mkdir()
    (models / "__init__.py").write_text("")
    (models / "order.py").write_text(
        "from sqlalchemy import Column, Integer, String\n"
        "from sqlalchemy.ext.declarative import declarative_base\n\n"
        "Base = declarative_base()\n\n"
        "class Order(Base):\n"
        "    __tablename__ = 'orders'\n"
        "    id = Column(Integer, primary_key=True)\n"
        "    status = Column(String)\n"
    )

    migrations = tmp_path / "src" / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    (migrations / "001_init.sql").write_text(
        "CREATE TABLE orders (\n"
        "    id SERIAL PRIMARY KEY,\n"
        "    customer_id UUID,\n"
        "    status VARCHAR(50),\n"
        "    total DECIMAL(10,2),\n"
        "    FOREIGN KEY (customer_id) REFERENCES customers(id)\n"
        ");\n"
    )

    return tmp_path


@pytest.fixture
def monorepo(tmp_path):
    """Create a monorepo with multiple services."""
    for svc_name in ("order-service", "user-service", "gateway"):
        svc = tmp_path / "services" / svc_name
        svc.mkdir(parents=True)
        (svc / "main.py").write_text(f"# {svc_name} entry point\nprint('hello')\n")
        (svc / "Dockerfile").write_text(f"FROM python:3.12\nCMD ['python', 'main.py']\n")
    (tmp_path / "docker-compose.yml").write_text(
        "version: '3'\n"
        "services:\n"
        "  order-service:\n"
        "    build: ./services/order-service\n"
        "  user-service:\n"
        "    build: ./services/user-service\n"
        "  gateway:\n"
        "    build: ./services/gateway\n"
        "  postgres:\n"
        "    image: postgres:15\n"
    )
    (tmp_path / "README.md").write_text("# Monorepo\nMulti-service project.")
    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """Create a JS/TS repo for non-Python extraction tests."""
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "my-app",
        "dependencies": {"express": "^4.18.0", "pg": "^8.11.0"},
        "devDependencies": {"jest": "^29.0.0"},
    }))
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        "import { Router } from 'express';\n"
        "import { Pool } from 'pg';\n\n"
        "export class UserService {\n"
        "  async getUsers() { return []; }\n"
        "}\n\n"
        "export interface UserResponse {\n"
        "  id: string;\n"
        "  name: string;\n"
        "}\n\n"
        "const router = Router();\n"
        "router.get('/users', async (req, res) => { res.json([]); });\n"
        "export default router;\n"
    )
    return tmp_path


@pytest.fixture
def go_repo(tmp_path):
    """Create a Go repo for Go extraction tests."""
    (tmp_path / "go.mod").write_text(
        "module github.com/example/myapp\n\n"
        "go 1.21\n\n"
        "require (\n"
        "\tgithub.com/gin-gonic/gin v1.9.0\n"
        "\tgithub.com/jackc/pgx/v5 v5.4.0\n"
        ")\n"
    )
    (tmp_path / "main.go").write_text(
        'package main\n\n'
        'import (\n'
        '\t"github.com/gin-gonic/gin"\n'
        ')\n\n'
        'type Server struct {\n'
        '\tPort int\n'
        '\tHost string\n'
        '}\n\n'
        'type Handler interface {\n'
        '\tHandle()\n'
        '}\n\n'
        'func (s *Server) Start() error {\n'
        '\treturn nil\n'
        '}\n\n'
        'func (s Server) Stop() {\n'
        '}\n\n'
        'func main() {\n'
        '\tr := gin.Default()\n'
        '\tr.Run()\n'
        '}\n'
    )
    return tmp_path


# ── clone_repo tests ──────────────────────────────────────────────────────────

class TestCloneRepo:
    def test_local_path_valid(self, sample_repo):
        result = clone_repo(str(sample_repo))
        assert "error" not in result
        assert result["repo_path"] == str(sample_repo)
        assert result["is_local"] is True

    def test_local_path_missing(self):
        result = clone_repo("/nonexistent/path/abc123")
        assert "error" in result

    def test_reject_file_url(self):
        result = clone_repo("file:///etc/passwd")
        assert "error" in result
        assert "Unsupported" in result["error"]

    def test_reject_ssh_url(self):
        result = clone_repo("ssh://attacker.com/repo")
        assert "error" in result
        assert "Unsupported" in result["error"]

    def test_reject_http_url(self):
        result = clone_repo("http://insecure.com/repo")
        assert "error" in result
        assert "Unsupported" in result["error"]

    def test_reject_ftp_url(self):
        result = clone_repo("ftp://files.com/repo.git")
        assert "error" in result
        assert "Unsupported" in result["error"]

    def test_https_clone_success(self):
        """Test HTTPS clone with mocked subprocess."""
        with patch("aion.tools.repo_analysis.subprocess.run") as mock_run, \
             patch("aion.tools.repo_analysis.os.path.isdir", return_value=False), \
             patch("aion.tools.repo_analysis.os.makedirs"), \
             patch("aion.tools.repo_analysis._dir_size_mb", return_value=5.0):
            mock_run.return_value = MagicMock(returncode=0)
            result = clone_repo("https://github.com/alice/myrepo.git")
            assert "error" not in result
            assert result["repo_name"] == "myrepo"
            assert result["repo_path"] == "/tmp/rta/alice/myrepo"
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "git"
            assert "--depth" in args

    def test_https_clone_failure(self):
        """Test HTTPS clone with git failure."""
        with patch("aion.tools.repo_analysis.subprocess.run") as mock_run, \
             patch("aion.tools.repo_analysis.os.path.isdir", return_value=False), \
             patch("aion.tools.repo_analysis.os.makedirs"):
            mock_run.return_value = MagicMock(returncode=128, stderr="fatal: repository not found")
            result = clone_repo("https://github.com/alice/nonexistent.git")
            assert "error" in result
            assert "clone failed" in result["error"].lower()


class TestExtractRepoIdentity:
    def test_https_with_git_suffix(self):
        identity, name = _extract_repo_identity("https://github.com/alice/myrepo.git")
        assert identity == "alice/myrepo"
        assert name == "myrepo"

    def test_https_without_suffix(self):
        identity, name = _extract_repo_identity("https://github.com/bob/fitting")
        assert identity == "bob/fitting"
        assert name == "fitting"

    def test_git_at_ssh(self):
        identity, name = _extract_repo_identity("git@github.com:org/project.git")
        assert identity == "org/project"
        assert name == "project"

    def test_no_collision(self):
        """Two repos with same name but different owners get different paths."""
        id1, _ = _extract_repo_identity("https://github.com/alice/app")
        id2, _ = _extract_repo_identity("https://github.com/bob/app")
        assert id1 != id2


# ── profile_repo tests ───────────────────────────────────────────────────────

class TestProfileRepo:
    def test_basic_profile(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        assert profile["repo_name"] == sample_repo.name
        assert profile["total_files"] > 0
        assert "Python" in [l["language"] for l in profile["tech_stack"]["languages"]]
        assert "fastapi" in profile["tech_stack"]["frameworks"]
        assert "Docker" in profile["tech_stack"]["containerization"]
        assert "docker-compose" in profile["tech_stack"]["containerization"]

    def test_file_tiers(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        assert profile["file_tier_counts"]["T1"] > 0
        assert profile["file_tier_counts"]["T2"] >= 0

    def test_database_detection(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        assert "PostgreSQL" in profile["tech_stack"]["databases"]
        assert "Redis" in profile["tech_stack"]["databases"]

    def test_structure_type(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        assert profile["structure_type"] == "single-service"

    def test_monorepo_detection(self, monorepo):
        profile = profile_repo(str(monorepo))
        assert profile["structure_type"] == "monorepo"

    def test_no_false_positive_substring(self, tmp_path):
        """Ensure short package names don't match inside longer words."""
        (tmp_path / "requirements.txt").write_text("upgrading\nmachinery\nchicken\n")
        profile = profile_repo(str(tmp_path))
        # "pg" should NOT match "upgrading", "chi" should NOT match "chicken"
        assert "PostgreSQL" not in profile["tech_stack"]["databases"]
        frameworks = profile["tech_stack"]["frameworks"]
        assert "chi" not in frameworks

    def test_views_dir_is_t3(self, tmp_path):
        """Non-entry-point files in views/ directories should be classified as T3 (skip)."""
        views = tmp_path / "result" / "views"
        views.mkdir(parents=True)
        (views / "layout.js").write_text("export class Layout { render() {} }")
        profile = profile_repo(str(tmp_path))
        for f in profile.get("architecturally_relevant_files", []):
            assert "views/" not in f["path"], f"views/ file should be T3, not {f['tier']}: {f['path']}"

    def test_templates_dir_is_t3(self, tmp_path):
        """Files in templates/ directories should be classified as T3 (skip)."""
        templates = tmp_path / "app" / "templates"
        templates.mkdir(parents=True)
        (templates / "base.html").write_text("<html></html>")
        (templates / "helper.py").write_text("def render(): pass")
        profile = profile_repo(str(tmp_path))
        for f in profile.get("architecturally_relevant_files", []):
            assert "templates/" not in f["path"], f"templates/ file should be T3: {f['path']}"


# ── extract_manifests tests ───────────────────────────────────────────────────

class TestExtractManifests:
    def test_docker_compose(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_manifests(str(sample_repo), profile)
        assert result.get("deployment_topology") is not None
        services = result["deployment_topology"]["services"]
        names = [s["name"] for s in services]
        assert "api" in names
        assert "postgres" in names
        assert "redis" in names

    def test_dockerfile(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_manifests(str(sample_repo), profile)
        assert len(result.get("dockerfiles", [])) > 0
        assert "python:3.12-slim" in result["dockerfiles"][0]["base_images"]

    def test_database_schemas(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_manifests(str(sample_repo), profile)
        schemas = result.get("database_schemas", [])
        assert len(schemas) > 0
        assert schemas[0]["tables"][0]["name"] == "orders"

    def test_package_dependencies(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_manifests(str(sample_repo), profile)
        pkg_deps = result.get("package_dependencies", [])
        assert len(pkg_deps) > 0
        assert "fastapi" in pkg_deps[0]["runtime_deps"]

    def test_readme_excerpt(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_manifests(str(sample_repo), profile)
        assert result.get("readme_excerpt") is not None
        assert "My Project" in result["readme_excerpt"]

    def test_empty_profile_no_crash(self, tmp_path):
        """Extracting from a repo with no T1 files should return empty sections."""
        (tmp_path / "hello.txt").write_text("hello")
        profile = profile_repo(str(tmp_path))
        result = extract_manifests(str(tmp_path), profile)
        # Should not crash, should return mostly empty
        assert isinstance(result, dict)

    def test_malformed_yaml_no_crash(self, tmp_path):
        """Malformed docker-compose should not crash extraction."""
        (tmp_path / "docker-compose.yml").write_text("this: is: not: valid: yaml: [[[")
        profile = profile_repo(str(tmp_path))
        result = extract_manifests(str(tmp_path), profile)
        assert isinstance(result, dict)


# ── extract_code_structure tests ──────────────────────────────────────────────

class TestExtractCodeStructure:
    def test_python_ast(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_code_structure(str(sample_repo), profile)
        assert result["stats"]["processed"] > 0
        assert len(result["modules"]) > 0

    def test_class_extraction(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_code_structure(str(sample_repo), profile)
        all_classes = []
        for mod in result["modules"]:
            for f in mod["files"]:
                all_classes.extend(f.get("classes", []))
        class_names = [c["name"] for c in all_classes]
        assert "Order" in class_names

    def test_import_extraction(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        result = extract_code_structure(str(sample_repo), profile)
        all_imports = []
        for mod in result["modules"]:
            for f in mod["files"]:
                all_imports.extend(f.get("imports", []))
        modules = [i["module"] for i in all_imports]
        assert any("fastapi" in m for m in modules)

    def test_js_ts_extraction(self, js_repo):
        profile = profile_repo(str(js_repo))
        result = extract_code_structure(str(js_repo), profile)
        assert result["stats"]["processed"] > 0
        all_classes = []
        all_imports = []
        for mod in result["modules"]:
            for f in mod["files"]:
                all_classes.extend(f.get("classes", []))
                all_imports.extend(f.get("imports", []))
        class_names = [c["name"] for c in all_classes]
        assert "UserService" in class_names
        import_modules = [i["module"] for i in all_imports]
        assert "express" in import_modules

    def test_go_extraction(self, go_repo):
        profile = profile_repo(str(go_repo))
        result = extract_code_structure(str(go_repo), profile)
        assert result["stats"]["processed"] > 0
        all_structs = []
        all_funcs = []
        for mod in result["modules"]:
            for f in mod["files"]:
                all_structs.extend(f.get("structs", []))
                all_funcs.extend(f.get("functions", []))
        struct_names = [s["name"] for s in all_structs]
        assert "Server" in struct_names
        # Check both pointer and value receivers are captured
        func_names = [fn["name"] for fn in all_funcs]
        assert "Start" in func_names
        assert "Stop" in func_names

    def test_go_value_receiver(self, go_repo):
        """Go value receivers should NOT have * prefix."""
        profile = profile_repo(str(go_repo))
        result = extract_code_structure(str(go_repo), profile)
        for mod in result["modules"]:
            for f in mod["files"]:
                for fn in f.get("functions", []):
                    if fn["name"] == "Stop":
                        # Stop has a value receiver: (s Server), not (s *Server)
                        assert "*" not in fn.get("receiver", ""), \
                            f"Value receiver should not have *: {fn['receiver']}"

    def test_syntax_error_no_crash(self, tmp_path):
        """Malformed Python should be skipped, not crash."""
        (tmp_path / "bad.py").write_text("def broken(\n  pass\n")
        profile = profile_repo(str(tmp_path))
        result = extract_code_structure(str(tmp_path), profile)
        assert result["stats"]["errors"] >= 1 or result["stats"]["skipped"] >= 0


# ── build_dep_graph tests ─────────────────────────────────────────────────────

class TestBuildDepGraph:
    def test_graph_nodes(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        node_ids = [n["id"] for n in graph["nodes"]]
        assert any(n.startswith("mod:") for n in node_ids)
        assert any(n.startswith("infra:") for n in node_ids)

    def test_graph_edges(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        assert len(graph["edges"]) > 0
        edge_types = {e["type"] for e in graph["edges"]}
        assert "data_access" in edge_types

    def test_empty_inputs_no_crash(self):
        """Build graph with empty inputs should not crash."""
        graph = build_dep_graph({"modules": []}, {})
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_evidence_strength_weak_depends_on(self, sample_repo):
        """depends_on edges without corroborating env vars should be 'weak'."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        for edge in graph["edges"]:
            assert "evidence_strength" in edge, f"Edge missing evidence_strength: {edge}"
        # depends_on edges that also have env var corroboration should be "strong"
        strong_edges = [e for e in graph["edges"] if e["evidence_strength"] == "strong"]
        weak_edges = [e for e in graph["edges"] if e["evidence_strength"] == "weak"]
        assert len(strong_edges) > 0, "Should have at least one strong edge"

    def test_evidence_strength_values(self, sample_repo):
        """All evidence_strength values should be 'strong' or 'weak'."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        for edge in graph["edges"]:
            assert edge["evidence_strength"] in ("strong", "weak"), \
                f"Unexpected evidence_strength: {edge['evidence_strength']}"


# ── merge_architecture_notes tests ────────────────────────────────────────────

class TestMergeArchitectureNotes:
    def test_full_merge(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        assert merged["type"] == "architecture_notes"
        assert merged["summary"]["repo_name"] == sample_repo.name
        assert len(merged["components"]) > 0
        assert len(merged["infrastructure"]) > 0

    def test_serializable(self, sample_repo):
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        serialized = json.dumps(merged, indent=2)
        assert len(serialized) > 100
        parsed = json.loads(serialized)
        assert parsed["type"] == "architecture_notes"

    def test_partial_data_merge(self):
        """Merge with minimal data should produce a valid result."""
        profile = {"repo_name": "test", "structure_type": "unknown",
                    "tech_stack": {"languages": [], "frameworks": [], "databases": [],
                                   "containerization": [], "iac": []},
                    "file_tier_counts": {"T1": 0, "T2": 0, "T3": 0}}
        manifests = {}
        code = {"modules": []}
        graph = {"nodes": [], "edges": []}
        merged = merge_architecture_notes(profile, manifests, code, graph)
        assert merged["type"] == "architecture_notes"
        assert merged["summary"]["repo_name"] == "test"
        assert merged["components"] == []

    def test_monorepo_merge(self, monorepo):
        profile = profile_repo(str(monorepo))
        manifests = extract_manifests(str(monorepo), profile)
        code = extract_code_structure(str(monorepo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        assert merged["summary"]["structure_type"] == "monorepo"
        assert merged["summary"]["total_components"] >= 3

    def test_v1_template_fields(self, sample_repo):
        """v1.0 template must include version, provenance, meta, edges, _deprecated."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        assert merged["version"] == TEMPLATE_VERSION
        assert "provenance" in merged
        assert "identity" in merged["provenance"]
        assert "temporal" in merged["provenance"]
        assert "context" in merged["provenance"]
        assert "meta" in merged
        assert merged["meta"]["repo_name"] == sample_repo.name
        assert "edges" in merged
        assert isinstance(merged["edges"], list)
        assert "_deprecated" in merged

    def test_merge_with_clone_context(self, sample_repo):
        """Passing clone_result populates meta and provenance.context."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        clone_result = {
            "repo_path": str(sample_repo),
            "repo_name": sample_repo.name,
            "repo_url": "https://github.com/test/repo",
            "branch": "feature/test",
            "commit_sha": "abc123def456" * 3 + "abcd",
            "default_branch": "main",
        }
        merged = merge_architecture_notes(
            profile, manifests, code, graph,
            clone_result=clone_result, base_branch="main",
        )
        assert merged["meta"]["branch"] == "feature/test"
        assert merged["meta"]["base_branch"] == "main"
        assert merged["provenance"]["context"]["commit_sha"] == clone_result["commit_sha"]
        assert merged["provenance"]["context"]["repo_url"] == "https://github.com/test/repo"

    def test_merge_with_diff_stats(self, sample_repo):
        """Diff stats populate the diff block and set changed flags on components."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        diff_stats = {
            "new": ["src/new_file.py"],
            "modified": ["src/main.py"],
            "deleted": ["old_file.py"],
        }
        merged = merge_architecture_notes(
            profile, manifests, code, graph,
            diff_stats=diff_stats, base_branch="main",
        )
        assert "diff" in merged
        assert merged["diff"]["new_files"] == 1
        assert merged["diff"]["modified_files"] == 1
        assert merged["diff"]["deleted_files"] == 1
        # Components should have changed flag
        for comp in merged["components"]:
            assert "changed" in comp

    def test_merge_backward_compat(self):
        """Calling with only positional args (no kwargs) still works and keeps deprecated fields."""
        profile = {"repo_name": "compat-test", "structure_type": "unknown",
                    "tech_stack": {"languages": [], "frameworks": [], "databases": [],
                                   "containerization": [], "iac": []},
                    "file_tier_counts": {"T1": 0, "T2": 0, "T3": 0}}
        manifests = {}
        code = {"modules": []}
        graph = {"nodes": [], "edges": []}
        merged = merge_architecture_notes(profile, manifests, code, graph)
        # Old fields still present
        assert merged["summary"]["repo_name"] == "compat-test"
        assert "external_services" in merged
        # New fields also present
        assert merged["version"] == TEMPLATE_VERSION
        assert "provenance" in merged
        assert "meta" in merged

    def test_component_role_inference(self, sample_repo):
        """Components with route decorators or api_endpoints should get role 'api'."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        allowed_roles = {"api", "service", "worker", "scheduler", "gateway"}
        api_found = False
        for comp in merged["components"]:
            assert "role" in comp
            assert comp["role"] in allowed_roles
            # Verify specific inference: components with route decorators → api
            has_routes = any(
                any(p in dec for p in (".get(", ".post(", ".put(", ".delete("))
                for kf in comp.get("key_functions", []) if isinstance(kf, dict)
                for dec in kf.get("decorators", [])
            )
            if has_routes or comp.get("api_endpoints"):
                assert comp["role"] == "api", (
                    f"Component '{comp['name']}' has routes but role={comp['role']!r}"
                )
                api_found = True
        assert api_found, "sample_repo should produce at least one component with role='api'"

    def test_edges_match_dep_graph(self, sample_repo):
        """Top-level edges count should match dep_graph edge count."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        merged = merge_architecture_notes(profile, manifests, code, graph)
        assert len(merged["edges"]) == len(graph["edges"])
        for edge in merged["edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "relation" in edge
            assert "evidence" in edge
            assert "evidence_strength" in edge

    def test_config_surface_strips_values(self):
        """config_surface must contain only key names, never values."""
        profile = {"repo_name": "test", "structure_type": "unknown",
                    "tech_stack": {"languages": [], "frameworks": [], "databases": [],
                                   "containerization": [], "iac": []},
                    "file_tier_counts": {"T1": 0, "T2": 0, "T3": 0}}
        manifests = {
            "deployment_topology": {
                "services": [
                    {"name": "postgres", "environment_keys": [
                        "POSTGRES_PASSWORD=secret123", "POSTGRES_DB=mydb", "PGDATA"
                    ]},
                ],
            },
        }
        code = {"modules": []}
        graph = {
            "nodes": [
                {"id": "infra:postgres", "name": "PostgreSQL", "type": "database", "image": "postgres:15"},
            ],
            "edges": [],
        }
        merged = merge_architecture_notes(profile, manifests, code, graph)
        for infra in merged["infrastructure"]:
            if infra["id"] == "infra:postgres":
                surface = infra.get("config_surface", [])
                for key in surface:
                    assert "=" not in key, f"config_surface leaked a value: {key}"
                    assert "secret" not in key.lower(), f"config_surface leaked a secret: {key}"
                assert "POSTGRES_PASSWORD" in surface
                assert "PGDATA" in surface


class TestGitDiffStats:
    def test_parse_name_status(self):
        """Verify parsing of git diff --name-status output."""
        fake_output = "A\tsrc/new.py\nM\tsrc/changed.py\nD\told.py\nR100\tsrc/renamed.py\n"
        with patch("aion.tools.repo_analysis.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            result = git_diff_stats("/fake/repo", "main")
        assert result["new"] == ["src/new.py"]
        assert result["modified"] == ["src/changed.py", "src/renamed.py"]
        assert result["deleted"] == ["old.py"]

    def test_command_failure_returns_empty(self):
        """Failed git command should return empty dict."""
        with patch("aion.tools.repo_analysis.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = git_diff_stats("/fake/repo", "main")
        assert result == {}

    def test_exception_returns_empty(self):
        """Subprocess exception should return empty dict."""
        with patch("aion.tools.repo_analysis.subprocess.run", side_effect=Exception("boom")):
            result = git_diff_stats("/fake/repo", "main")
        assert result == {}


class TestGoldenYamlStructure:
    """Snapshot test that validates the full YAML structure shape."""

    def test_golden_structure(self, sample_repo):
        """All required top-level keys and nested structure must be present."""
        profile = profile_repo(str(sample_repo))
        manifests = extract_manifests(str(sample_repo), profile)
        code = extract_code_structure(str(sample_repo), profile)
        graph = build_dep_graph(code, manifests)
        clone_result = {
            "repo_path": str(sample_repo), "repo_name": sample_repo.name,
            "repo_url": "https://github.com/test/repo",
            "branch": "main", "commit_sha": "a" * 40, "default_branch": "main",
        }
        merged = merge_architecture_notes(
            profile, manifests, code, graph,
            clone_result=clone_result, base_branch="main",
            diff_stats={"new": [], "modified": ["src/main.py"], "deleted": []},
        )

        # Top-level keys
        required_top = {"type", "version", "provenance", "meta", "summary",
                        "components", "edges", "infrastructure", "external_services",
                        "_deprecated"}
        assert required_top.issubset(set(merged.keys())), \
            f"Missing top-level keys: {required_top - set(merged.keys())}"

        # Provenance structure
        prov = merged["provenance"]
        assert set(prov.keys()) == {"identity", "temporal", "context"}
        assert "display_name" in prov["identity"]
        assert "access_time" in prov["temporal"]
        assert "commit_sha" in prov["context"]

        # Meta structure
        meta = merged["meta"]
        assert set(meta.keys()) == {"repo_name", "branch", "base_branch", "analyzer_version"}

        # Component structure (at least one component)
        assert len(merged["components"]) > 0
        comp = merged["components"][0]
        assert "id" in comp
        assert "role" in comp
        assert "changed" in comp

        # Edge structure (if edges exist)
        if merged["edges"]:
            edge = merged["edges"][0]
            assert set(edge.keys()) == {"from", "to", "relation", "evidence", "evidence_strength"}

        # Diff block
        assert "diff" in merged
        diff = merged["diff"]
        assert set(diff.keys()) == {"base_branch", "new_files", "modified_files",
                                     "deleted_files", "changed_components"}

        # Serializable
        serialized = json.dumps(merged, indent=2)
        assert json.loads(serialized)["version"] == TEMPLATE_VERSION


# ── Branch URL parsing ────────────────────────────────────────────────────────


class TestExtractBranchFromUrl:
    """Tests for _extract_branch_from_url()."""

    def test_tree_url_extracts_branch(self):
        url = "https://github.com/Org/repo/tree/feature/foo"
        clean, branch = _extract_branch_from_url(url)
        assert clean == "https://github.com/Org/repo"
        assert branch == "feature/foo"

    def test_tree_url_simple_branch(self):
        url = "https://github.com/Org/repo/tree/main"
        clean, branch = _extract_branch_from_url(url)
        assert clean == "https://github.com/Org/repo"
        assert branch == "main"

    def test_blob_url_returns_none_branch(self):
        """blob URLs mix branch + file path — can't reliably extract branch."""
        url = "https://github.com/Org/repo/blob/main/README.md"
        clean, branch = _extract_branch_from_url(url)
        assert clean == "https://github.com/Org/repo"
        assert branch is None

    def test_plain_url_no_branch(self):
        url = "https://github.com/Org/repo"
        clean, branch = _extract_branch_from_url(url)
        assert clean == url
        assert branch is None

    def test_git_suffix_no_branch(self):
        url = "https://github.com/Org/repo.git"
        clean, branch = _extract_branch_from_url(url)
        assert clean == url
        assert branch is None

    def test_tree_url_with_slashes_in_branch(self):
        url = "https://github.com/Org/repo/tree/feature/foo/bar"
        clean, branch = _extract_branch_from_url(url)
        assert clean == "https://github.com/Org/repo"
        assert branch == "feature/foo/bar"

    def test_identity_from_tree_url(self):
        """_extract_repo_identity should handle /tree/ URLs correctly."""
        url = "https://github.com/Alliander/esa-ainstein-artifacts/tree/feature/archimate"
        identity, name = _extract_repo_identity(url)
        assert identity == "Alliander/esa-ainstein-artifacts"
        assert name == "esa-ainstein-artifacts"

    def test_identity_from_blob_url(self):
        url = "https://github.com/Org/repo/blob/main/src/app.py"
        identity, name = _extract_repo_identity(url)
        assert identity == "Org/repo"
        assert name == "repo"


# ── Module detection (3-level grouping) ───────────────────────────────────────


class TestDetectModules:
    """Tests for _detect_modules() 3-level path grouping.

    Tests call profile_repo() which invokes _detect_modules() internally
    with the correct internal file_index format, then checks the returned
    modules list.
    """

    @pytest.fixture()
    def repo_with_subpackages(self, tmp_path):
        """Create a repo structure with nested Python subpackages."""
        # src/aion/ — package root files
        (tmp_path / "src" / "aion").mkdir(parents=True)
        (tmp_path / "src" / "aion" / "__init__.py").write_text("")
        (tmp_path / "src" / "aion" / "chat_ui.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        (tmp_path / "src" / "aion" / "config.py").write_text("import os\nDEBUG = True")
        # src/aion/agents/ — subpackage
        (tmp_path / "src" / "aion" / "agents").mkdir()
        (tmp_path / "src" / "aion" / "agents" / "__init__.py").write_text("")
        (tmp_path / "src" / "aion" / "agents" / "rag_agent.py").write_text("class RAGAgent: pass")
        (tmp_path / "src" / "aion" / "agents" / "vocab_agent.py").write_text("class VocabAgent: pass")
        # src/aion/tools/ — subpackage
        (tmp_path / "src" / "aion" / "tools").mkdir()
        (tmp_path / "src" / "aion" / "tools" / "__init__.py").write_text("")
        (tmp_path / "src" / "aion" / "tools" / "search.py").write_text("def search(): pass")
        (tmp_path / "src" / "aion" / "tools" / "archimate.py").write_text("def validate(): pass")
        # pyproject.toml at root (needed for module detection)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')
        return tmp_path

    def test_subpackages_are_separate_modules(self, repo_with_subpackages):
        """src/aion/agents/ and src/aion/tools/ must be separate modules,
        not collapsed into src/aion."""
        profile = profile_repo(str(repo_with_subpackages))
        mod_paths = {m["path"] for m in profile.get("modules", [])}

        assert "src/aion/agents" in mod_paths, f"agents missing from {mod_paths}"
        assert "src/aion/tools" in mod_paths, f"tools missing from {mod_paths}"
        assert "src/aion" in mod_paths, f"src/aion missing from {mod_paths}"

    def test_root_level_files_excluded(self, repo_with_subpackages):
        """Single files at root (e.g., main.py) should not create a module."""
        (repo_with_subpackages / "main.py").write_text("print('hello')")
        profile = profile_repo(str(repo_with_subpackages))
        mod_paths = {m["path"] for m in profile.get("modules", [])}

        assert "(root)" not in mod_paths

    def test_module_has_correct_file_count(self, repo_with_subpackages):
        """Each module's file_count should match the files in that subpackage."""
        profile = profile_repo(str(repo_with_subpackages))
        by_path = {m["path"]: m for m in profile.get("modules", [])}

        # agents/ has __init__.py + rag_agent.py + vocab_agent.py = 3 files
        assert by_path["src/aion/agents"]["file_count"] >= 2
        # tools/ has __init__.py + search.py + archimate.py = 3 files
        assert by_path["src/aion/tools"]["file_count"] >= 2
