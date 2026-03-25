"""Repository extraction tools — manifests, AST, dependency graph.

Deterministic parsers for architecturally dense files. Zero LLM tokens.
Logic ported from draft scripts 03, 04, 05 in
docs/.local/archimate-repo-skill-upgrade/.
"""

import ast
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Safe YAML loading ─────────────────────────────────────────────────────────

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def _safe_load_yaml(filepath):
    if not _HAS_YAML:
        return _fallback_yaml_parse(filepath)
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _fallback_yaml_parse(filepath):
    """Minimal YAML-like parser for docker-compose when PyYAML is unavailable.

    Handles: services (image, build, ports, depends_on, environment), networks, volumes.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        result = {"services": {}, "networks": {}, "volumes": {}}
        current_section = None
        current_service = None
        current_key = None  # tracks list-valued keys like ports, depends_on
        for line in content.split("\n"):
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0 and stripped.endswith(":"):
                key = stripped[:-1].strip()
                if key in ("services", "networks", "volumes"):
                    current_section = key
                    current_service = None
                    current_key = None
                else:
                    current_section = None
                continue
            if current_section == "services" and indent == 2 and stripped.endswith(":"):
                svc_name = stripped[:-1].strip()
                result["services"][svc_name] = {
                    "ports": [], "depends_on": [], "environment": {},
                }
                current_service = svc_name
                current_key = None
                continue
            if current_service and indent == 4:
                svc = result["services"][current_service]
                if stripped.startswith("- "):
                    # List item under current_key
                    val = stripped[2:].strip()
                    if current_key == "ports":
                        svc.setdefault("ports", []).append(val)
                    elif current_key == "depends_on":
                        svc.setdefault("depends_on", []).append(val)
                    continue
                kv = stripped.split(":", 1)
                if len(kv) == 2:
                    k = kv[0].strip()
                    v = kv[1].strip()
                    if k in ("image", "build"):
                        svc[k] = v
                        current_key = None
                    elif k in ("ports", "depends_on", "environment", "networks", "volumes"):
                        current_key = k
                    else:
                        current_key = None
            elif current_service and indent == 6 and stripped.startswith("- "):
                val = stripped[2:].strip()
                svc = result["services"][current_service]
                if current_key == "ports":
                    svc.setdefault("ports", []).append(val)
                elif current_key == "depends_on":
                    svc.setdefault("depends_on", []).append(val)
                elif current_key == "environment" and "=" in val:
                    env_key = val.split("=", 1)[0]
                    svc.setdefault("environment", {})[env_key] = ""
            elif current_service and indent == 6 and current_key == "environment":
                kv = stripped.split(":", 1)
                if len(kv) == 2:
                    svc = result["services"][current_service]
                    svc.setdefault("environment", {})[kv[0].strip()] = kv[1].strip()
        return result
    except Exception:
        return None


def _read_file(filepath, max_bytes=50000):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except (OSError, UnicodeDecodeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MANIFEST EXTRACTION (from 03_extract_manifests.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_docker_compose(filepath):
    data = _safe_load_yaml(filepath)
    if not data or not isinstance(data, dict):
        return None
    services = []
    for svc_name, svc_conf in (data.get("services") or {}).items():
        if not isinstance(svc_conf, dict):
            continue
        image = svc_conf.get("image", "")
        build = svc_conf.get("build", "")
        if isinstance(build, dict):
            build = build.get("context", "")
        ports = [str(p) for p in (svc_conf.get("ports") or [])]
        depends_on = []
        dep = svc_conf.get("depends_on")
        if isinstance(dep, list):
            depends_on = dep
        elif isinstance(dep, dict):
            depends_on = list(dep.keys())
        env_keys = []
        env = svc_conf.get("environment")
        if isinstance(env, dict):
            env_keys = list(env.keys())
        elif isinstance(env, list):
            for e in env:
                if "=" in str(e):
                    env_keys.append(str(e).split("=", 1)[0])
        networks = list(svc_conf.get("networks") or [])
        if isinstance(svc_conf.get("networks"), dict):
            networks = list(svc_conf["networks"].keys())
        volumes = [str(v).split(":")[0] if ":" in str(v) else str(v)
                   for v in (svc_conf.get("volumes") or [])]
        services.append({
            "name": svc_name,
            "image_or_build": image if image else str(build),
            "ports": ports, "depends_on": depends_on,
            "environment_keys": env_keys[:20], "networks": networks, "volumes": volumes,
        })
    return {
        "source_file": filepath,
        "services": services,
        "networks": list((data.get("networks") or {}).keys()),
        "volumes": list((data.get("volumes") or {}).keys()),
    }


def _parse_dockerfile(filepath):
    content = _read_file(filepath, 10000)
    if not content:
        return None
    return {
        "source_file": filepath,
        "base_images": re.findall(r"^FROM\s+(\S+)", content, re.MULTILINE),
        "exposed_ports": [p.strip() for p in re.findall(r"^EXPOSE\s+(.+)", content, re.MULTILINE)],
        "cmd": (re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)", content, re.MULTILINE) or [None])[-1],
        "workdir": (re.findall(r"^WORKDIR\s+(\S+)", content, re.MULTILINE) or [None])[-1],
    }


def _parse_openapi(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".yaml", ".yml"):
        data = _safe_load_yaml(filepath)
    else:
        content = _read_file(filepath)
        if not content:
            return None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not data or not isinstance(data, dict):
        return None
    info = data.get("info", {})
    endpoints = []
    for path, methods in (data.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                summary = ""
                if isinstance(details, dict):
                    summary = details.get("summary", details.get("description", ""))
                    if summary and len(summary) > 100:
                        summary = summary[:100] + "..."
                endpoints.append({"method": method.upper(), "path": path, "summary": summary})
    return {"source_file": filepath, "title": info.get("title", ""),
            "version": info.get("version", ""), "endpoints": endpoints}


def _parse_protobuf(filepath):
    content = _read_file(filepath, 20000)
    if not content:
        return None
    services = []
    for match in re.finditer(r"service\s+(\w+)\s*\{([^}]+)\}", content):
        rpcs = re.findall(r"rpc\s+(\w+)\s*\((\w+)\)\s*returns\s*\((\w+)\)", match.group(2))
        services.append({
            "name": match.group(1),
            "rpcs": [{"name": r[0], "request": r[1], "response": r[2]} for r in rpcs],
        })
    messages = re.findall(r"message\s+(\w+)\s*\{", content)
    package = re.search(r"package\s+([\w.]+)\s*;", content)
    return {"source_file": filepath, "package": package.group(1) if package else None,
            "services": services, "message_types": messages}


def _parse_graphql(filepath):
    content = _read_file(filepath, 20000)
    if not content:
        return None
    return {
        "source_file": filepath,
        "types": re.findall(r"type\s+(\w+)", content),
        "inputs": re.findall(r"input\s+(\w+)", content),
        "enums": re.findall(r"enum\s+(\w+)", content),
        "fields": re.findall(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*[\w!\[\]]+", content)[:30],
    }


def _parse_terraform(filepath):
    content = _read_file(filepath, 30000)
    if not content:
        return None
    resources = [{"type": m.group(1), "name": m.group(2)}
                 for m in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content)]
    providers = re.findall(r'provider\s+"([^"]+)"', content)
    data_sources = [{"type": m.group(1), "name": m.group(2)}
                    for m in re.finditer(r'data\s+"([^"]+)"\s+"([^"]+)"', content)]
    modules = [m.group(1) for m in re.finditer(r'module\s+"([^"]+)"', content)]
    if not resources and not data_sources and not modules:
        return None
    return {"source_file": filepath, "provider": providers[0] if providers else None,
            "resources": resources, "data_sources": data_sources, "modules": modules}


def _parse_sql_migration(filepath):
    content = _read_file(filepath, 30000)
    if not content:
        return None
    tables = []
    for match in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\(([^;]+)\)",
        content, re.IGNORECASE | re.DOTALL,
    ):
        table_name = match.group(1)
        body = match.group(2)
        columns, foreign_keys = [], []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            fk_match = re.search(
                r"FOREIGN\s+KEY\s*\([`\"']?(\w+)[`\"']?\)\s*REFERENCES\s+[`\"']?(\w+)[`\"']?\s*\([`\"']?(\w+)[`\"']?\)",
                line, re.IGNORECASE,
            )
            if fk_match:
                foreign_keys.append({"column": fk_match.group(1),
                                     "references": f"{fk_match.group(2)}.{fk_match.group(3)}"})
                continue
            col_match = re.match(r"[`\"']?(\w+)[`\"']?\s+(\w[\w()]+)", line)
            if col_match:
                col_name_upper = col_match.group(1).upper()
                if col_name_upper in ("PRIMARY", "UNIQUE", "INDEX", "KEY", "CONSTRAINT", "CHECK", "FOREIGN"):
                    continue
                col_str = f"{col_match.group(1)} {col_match.group(2)}"
                if "PRIMARY KEY" in line.upper():
                    col_str += " PK"
                if "REFERENCES" in line.upper():
                    col_str += " FK"
                    ref = re.search(r"REFERENCES\s+[`\"']?(\w+)[`\"']?\s*\([`\"']?(\w+)[`\"']?\)", line, re.I)
                    if ref:
                        foreign_keys.append({"column": col_match.group(1),
                                             "references": f"{ref.group(1)}.{ref.group(2)}"})
                columns.append(col_str)
        if columns:
            tables.append({"name": table_name, "columns": columns[:20], "foreign_keys": foreign_keys})
    return {"source_file": filepath, "tables": tables} if tables else None


def _parse_ci_config(filepath):
    data = _safe_load_yaml(filepath)
    if not data or not isinstance(data, dict):
        return None
    result = {"source_file": filepath}
    if "jobs" in data:
        result["type"] = "github_actions"
        trigger = data.get("on", {})
        if isinstance(trigger, str):
            result["triggers"] = [trigger]
        elif isinstance(trigger, list):
            result["triggers"] = trigger
        elif isinstance(trigger, dict):
            result["triggers"] = list(trigger.keys())
        else:
            result["triggers"] = []
        jobs = []
        for job_name, job_conf in data["jobs"].items():
            if isinstance(job_conf, dict):
                steps = [s.get("name", s.get("uses", s.get("run", "")[:50]))
                         for s in job_conf.get("steps", []) if isinstance(s, dict)]
                jobs.append({"name": job_name, "steps": steps[:10]})
            else:
                jobs.append({"name": job_name, "steps": []})
        result["jobs"] = jobs
    elif "stages" in data:
        result["type"] = "gitlab_ci"
        result["stages"] = data["stages"]
        jobs = [k for k in data if k not in ("stages", "variables", "default", "include", "image")]
        result["jobs"] = [{"name": j} for j in jobs[:15]]
    return result


def _parse_requirements_txt(filepath):
    content = _read_file(filepath, 10000)
    if not content:
        return None
    deps = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = re.split(r"[>=<!\[;]", line)[0].strip()
        if pkg:
            deps.append(pkg)
    return deps


def _parse_package_json(filepath):
    content = _read_file(filepath)
    if not content:
        return None, None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None, None
    return list((data.get("dependencies") or {}).keys()), list((data.get("devDependencies") or {}).keys())


def _parse_go_mod(filepath):
    content = _read_file(filepath, 10000)
    if not content:
        return None
    deps = []
    in_require = False
    for line in content.split("\n"):
        line = line.strip()
        if line == "require (":
            in_require = True
            continue
        if line == ")" and in_require:
            in_require = False
            continue
        if in_require and line:
            parts = line.split()
            if parts:
                deps.append(parts[0])
        elif line.startswith("require "):
            parts = line.split()
            if len(parts) >= 2:
                deps.append(parts[1])
    return deps


def _extract_readme(repo_path):
    for name in ("ARCHITECTURE.md", "DESIGN.md", "README.md", "README.rst", "README.txt", "README"):
        fpath = os.path.join(repo_path, name)
        if os.path.isfile(fpath):
            content = _read_file(fpath, 1000)
            if content:
                content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
                content = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", content)
                return content.strip()[:500]
    return None


def extract_manifests(repo_path: str, profile: dict) -> dict:
    """Extract structured info from architecturally dense files."""
    result = {
        "deployment_topology": None,
        "dockerfiles": [], "api_definitions": [], "protobuf_services": [],
        "graphql_schemas": [], "infrastructure": [], "database_schemas": [],
        "ci_cd_pipelines": [], "package_dependencies": [],
        "readme_excerpt": _extract_readme(repo_path),
    }

    for file_info in profile.get("architecturally_relevant_files", []):
        if file_info["tier"] != "T1":
            continue
        rel_path = file_info["path"]
        full_path = os.path.join(repo_path, rel_path)
        category = file_info["category"]
        if not os.path.isfile(full_path):
            continue
        filename = os.path.basename(rel_path).lower()

        try:
            if category == "deployment" and "compose" in filename:
                parsed = _parse_docker_compose(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["deployment_topology"] = parsed
            elif category == "containerization" and "dockerfile" in filename:
                parsed = _parse_dockerfile(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["dockerfiles"].append(parsed)
            elif category == "api_definition" and ("openapi" in filename or "swagger" in filename):
                parsed = _parse_openapi(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["api_definitions"].append(parsed)
            elif category == "api_definition" and rel_path.endswith(".proto"):
                parsed = _parse_protobuf(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["protobuf_services"].append(parsed)
            elif category == "api_definition" and rel_path.endswith((".graphql", ".gql")):
                parsed = _parse_graphql(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["graphql_schemas"].append(parsed)
            elif category == "iac" and rel_path.endswith(".tf"):
                parsed = _parse_terraform(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["infrastructure"].append(parsed)
            elif category == "data_schema" and rel_path.endswith(".sql"):
                parsed = _parse_sql_migration(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["database_schemas"].append(parsed)
            elif category == "ci_cd" and rel_path.endswith((".yml", ".yaml")):
                parsed = _parse_ci_config(full_path)
                if parsed:
                    parsed["source_file"] = rel_path
                    result["ci_cd_pipelines"].append(parsed)
        except Exception:
            logger.warning("Failed to parse %s", rel_path, exc_info=True)

    # Package dependencies
    for file_info in profile.get("architecturally_relevant_files", []):
        rel_path = file_info["path"]
        full_path = os.path.join(repo_path, rel_path)
        filename = os.path.basename(rel_path)
        if not os.path.isfile(full_path):
            continue
        module_path = str(Path(rel_path).parent)
        if module_path == ".":
            module_path = "(root)"

        try:
            if filename == "requirements.txt":
                deps = _parse_requirements_txt(full_path)
                if deps:
                    result["package_dependencies"].append(
                        {"source_file": rel_path, "module": module_path, "format": "pip", "runtime_deps": deps})
            elif filename == "package.json":
                runtime, dev = _parse_package_json(full_path)
                if runtime is not None:
                    result["package_dependencies"].append(
                        {"source_file": rel_path, "module": module_path, "format": "npm",
                         "runtime_deps": runtime, "dev_deps": dev})
            elif filename == "go.mod":
                deps = _parse_go_mod(full_path)
                if deps:
                    result["package_dependencies"].append(
                        {"source_file": rel_path, "module": module_path, "format": "go", "runtime_deps": deps})
        except Exception:
            logger.warning("Failed to parse deps from %s", rel_path, exc_info=True)

    return {k: v for k, v in result.items() if v}


# ═══════════════════════════════════════════════════════════════════════════════
# AST / CODE STRUCTURE EXTRACTION (from 04_ast_extract.py)
# ═══════════════════════════════════════════════════════════════════════════════

class _PythonExtractor(ast.NodeVisitor):
    """Extract structural info from Python files using the ast module."""

    def __init__(self):
        self.imports = []
        self.classes = []
        self.functions = []
        self.decorated_functions = []
        self.type_definitions = []
        self.constants = []
        self.exports = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({"module": alias.name, "names": [alias.asname or alias.name]})
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        names = [a.name for a in node.names]
        if node.level:
            module = "." * node.level + module
        self.imports.append({"module": module, "names": names})
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base))
        methods = []
        class_vars = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = self._extract_params(item)
                returns = self._extract_return(item)
                decorators = [self._decorator_str(d) for d in item.decorator_list]
                methods.append({
                    "name": item.name, "params": params, "returns": returns,
                    "decorators": decorators, "is_async": isinstance(item, ast.AsyncFunctionDef),
                })
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                ann = ast.unparse(item.annotation) if item.annotation else None
                class_vars.append({"name": item.target.id, "type": ann})
        decorators = [self._decorator_str(d) for d in node.decorator_list]
        self.classes.append({
            "name": node.name, "bases": bases, "decorators": decorators,
            "methods": methods, "class_variables": class_vars[:10],
        })

    def visit_FunctionDef(self, node):
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node, is_async=True)

    def _handle_function(self, node, is_async):
        params = self._extract_params(node)
        returns = self._extract_return(node)
        decorators = [self._decorator_str(d) for d in node.decorator_list]
        func_info = {"name": node.name, "params": params, "returns": returns,
                     "decorators": decorators, "is_async": is_async}
        if decorators:
            self.decorated_functions.append(func_info)
        else:
            self.functions.append(func_info)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if name == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            self.exports.append(elt.value)
                elif name.isupper() and isinstance(node.value, ast.Constant):
                    val = repr(node.value.value)
                    if len(val) > 60:
                        val = val[:60] + "..."
                    self.constants.append(f"{name} = {val}")
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            name = node.target.id
            ann = ast.unparse(node.annotation) if node.annotation else None
            if ann and name[0].isupper():
                self.type_definitions.append(f"{name}: {ann}")

    def _extract_params(self, func_node):
        params = []
        args = func_node.args
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            p = arg.arg
            if arg.annotation:
                p += f": {ast.unparse(arg.annotation)}"
            if i >= defaults_offset:
                default = args.defaults[i - defaults_offset]
                p += f" = {repr(default.value)}" if isinstance(default, ast.Constant) else " = ..."
            params.append(p)
        if args.vararg:
            p = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                p += f": {ast.unparse(args.vararg.annotation)}"
            params.append(p)
        if args.kwarg:
            p = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                p += f": {ast.unparse(args.kwarg.annotation)}"
            params.append(p)
        return params

    def _extract_return(self, func_node):
        return ast.unparse(func_node.returns) if func_node.returns else None

    def _decorator_str(self, decorator):
        return "@" + ast.unparse(decorator)


def _extract_python(filepath, tier):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    extractor = _PythonExtractor()
    if tier == "T1":
        extractor.visit(tree)
    else:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                extractor.visit(node)
            elif isinstance(node, ast.ClassDef):
                extractor.classes.append({
                    "name": node.name,
                    "bases": [ast.unparse(b) for b in node.bases if isinstance(b, (ast.Name, ast.Attribute))],
                    "decorators": [extractor._decorator_str(d) for d in node.decorator_list],
                    "methods": [item.name for item in node.body
                                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))],
                    "class_variables": [],
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                extractor.functions.append({"name": node.name})
    result = {"imports": extractor.imports}
    if extractor.classes:
        result["classes"] = extractor.classes
    if extractor.functions:
        result["functions"] = extractor.functions
    if extractor.decorated_functions:
        result["decorated_functions"] = extractor.decorated_functions
    if extractor.exports:
        result["exports"] = extractor.exports
    if extractor.type_definitions:
        result["type_definitions"] = extractor.type_definitions
    if extractor.constants:
        result["constants"] = extractor.constants[:15]
    return result


def _extract_js_ts(filepath, tier):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(100000)
    except (OSError, UnicodeDecodeError):
        return None
    result = {}
    imports = []
    for m in re.finditer(r'import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]', content):
        names = m.group(1) or m.group(2)
        name_list = [n.strip().split(" as ")[0].strip() for n in names.split(",")] if m.group(1) else [names]
        imports.append({"module": m.group(3), "names": name_list})
    for m in re.finditer(r'import\s+(\w+)\s*,\s*\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]', content):
        names = [m.group(1)] + [n.strip().split(" as ")[0].strip() for n in m.group(2).split(",")]
        imports.append({"module": m.group(3), "names": names})
    for m in re.finditer(r'(?:const|let|var)\s+(?:\{([^}]+)\}|(\w+))\s*=\s*require\([\'"]([^\'"]+)[\'"]\)', content):
        names = m.group(1) or m.group(2)
        name_list = [n.strip() for n in names.split(",")] if m.group(1) else [names]
        imports.append({"module": m.group(3), "names": name_list})
    result["imports"] = imports

    if tier == "T2":
        classes = re.findall(r'(?:export\s+)?class\s+(\w+)', content)
        functions = re.findall(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', content)
        if classes:
            result["classes"] = [{"name": c} for c in classes]
        if functions:
            result["functions"] = [{"name": f} for f in functions]
        return result

    classes = []
    for m in re.finditer(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', content):
        classes.append({"name": m.group(1), "bases": [m.group(2)] if m.group(2) else []})
    if classes:
        result["classes"] = classes
    functions = []
    for m in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', content):
        functions.append({"name": m.group(1), "params": [p.strip() for p in m.group(2).split(",") if p.strip()]})
    for m in re.finditer(r'(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*\w+)?\s*=>', content):
        functions.append({"name": m.group(1), "params": [p.strip() for p in m.group(2).split(",") if p.strip()]})
    if functions:
        result["functions"] = functions
    exports = []
    for m in re.finditer(r'export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)', content):
        exports.append(m.group(1))
    if exports:
        result["exports"] = exports
    routes = []
    for m in re.finditer(r'(?:app|router)\.(get|post|put|patch|delete)\s*\([\'"]([^\'"]+)[\'"]', content):
        routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    if routes:
        result["route_registrations"] = routes[:20]
    interfaces = []
    for m in re.finditer(r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?', content):
        interfaces.append({"name": m.group(1), "extends": m.group(2).strip() if m.group(2) else None})
    if interfaces:
        result["interfaces"] = interfaces
    return result


def _extract_java(filepath, tier):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(100000)
    except (OSError, UnicodeDecodeError):
        return None
    result = {}
    pkg = re.search(r'package\s+([\w.]+)\s*;', content)
    if pkg:
        result["package"] = pkg.group(1)
    imports = re.findall(r'import\s+([\w.*]+)\s*;', content)
    if imports:
        result["imports"] = [{"module": imp} for imp in imports]
    classes = []
    for m in re.finditer(
        r'(?:@(\w+)(?:\([^)]*\))?\s*\n\s*)?(?:public\s+|private\s+|protected\s+)?(?:abstract\s+)?'
        r'(class|interface|enum)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?',
        content,
    ):
        cls = {"name": m.group(3), "kind": m.group(2)}
        if m.group(1):
            cls["annotation"] = f"@{m.group(1)}"
        if m.group(4):
            cls["extends"] = m.group(4)
        if m.group(5):
            cls["implements"] = [i.strip() for i in m.group(5).split(",")]
        classes.append(cls)
    if classes:
        result["classes"] = classes
    if tier == "T2":
        return result
    methods = []
    for m in re.finditer(
        r'(?:@(\w+)(?:\([^)]*\))?\s*\n\s*)?(?:public|private|protected)\s+(?:static\s+)?(?:abstract\s+)?'
        r'([\w<>\[\]]+)\s+(\w+)\s*\(([^)]*)\)',
        content,
    ):
        method = {"name": m.group(3), "returns": m.group(2),
                  "params": [p.strip() for p in m.group(4).split(",") if p.strip()]}
        if m.group(1):
            method["annotation"] = f"@{m.group(1)}"
        methods.append(method)
    if methods:
        result["methods"] = methods[:30]
    return result


def _extract_go(filepath, tier):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(100000)
    except (OSError, UnicodeDecodeError):
        return None
    result = {}
    pkg = re.search(r'package\s+(\w+)', content)
    if pkg:
        result["package"] = pkg.group(1)
    imports = []
    for m in re.finditer(r'import\s+"([^"]+)"', content):
        imports.append({"module": m.group(1)})
    for m in re.finditer(r'import\s+\(([^)]+)\)', content, re.DOTALL):
        for line in m.group(1).split("\n"):
            line = line.strip().strip('"')
            if line and not line.startswith("//"):
                parts = line.split()
                if len(parts) >= 2:
                    imports.append({"module": parts[-1].strip('"'), "alias": parts[0]})
                elif parts:
                    imports.append({"module": parts[0].strip('"')})
    if imports:
        result["imports"] = imports
    structs = []
    for m in re.finditer(r'type\s+(\w+)\s+struct\s*\{([^}]*)\}', content, re.DOTALL):
        fields = []
        for line in m.group(2).split("\n"):
            line = line.strip()
            if line and not line.startswith("//"):
                parts = line.split()
                if len(parts) >= 2:
                    fields.append(f"{parts[0]} {parts[1]}")
        structs.append({"name": m.group(1), "fields": fields[:15]})
    if structs:
        result["structs"] = structs
    interfaces = []
    for m in re.finditer(r'type\s+(\w+)\s+interface\s*\{([^}]*)\}', content, re.DOTALL):
        methods = re.findall(r'(\w+)\s*\(', m.group(2))
        interfaces.append({"name": m.group(1), "methods": methods})
    if interfaces:
        result["interfaces"] = interfaces
    if tier == "T2":
        return result
    functions = []
    for m in re.finditer(
        r'func\s+(?:\((\w+)\s+(\*?)(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)(?:\s*\(([^)]*)\)|\s*([\w*\[\]]+))?',
        content,
    ):
        func = {"name": m.group(4)}
        if m.group(1) and m.group(3):
            ptr = m.group(2)  # "*" or ""
            func["receiver"] = f"({m.group(1)} {ptr}{m.group(3)})"
        params = m.group(5).strip()
        if params:
            func["params"] = [p.strip() for p in params.split(",")]
        returns = m.group(6) or m.group(7)
        if returns:
            func["returns"] = returns.strip()
        functions.append(func)
    if functions:
        result["functions"] = functions[:30]
    return result


def _extract_generic(filepath, language, tier):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(100000)
    except (OSError, UnicodeDecodeError):
        return None
    result = {}
    if language == "Rust":
        uses = re.findall(r'use\s+([\w:{}*,\s]+)\s*;', content)
        if uses:
            result["imports"] = [{"module": u.strip()} for u in uses]
        structs = re.findall(r'(?:pub\s+)?struct\s+(\w+)', content)
        enums = re.findall(r'(?:pub\s+)?enum\s+(\w+)', content)
        traits = re.findall(r'(?:pub\s+)?trait\s+(\w+)', content)
        if structs:
            result["structs"] = [{"name": s} for s in structs]
        if enums:
            result["enums"] = enums
        if traits:
            result["traits"] = traits
        if tier == "T1":
            impls = re.findall(r'impl(?:\s+\w+\s+for)?\s+(\w+)', content)
            if impls:
                result["impl_blocks"] = list(set(impls))
    elif language == "C#":
        usings = re.findall(r'using\s+([\w.]+)\s*;', content)
        if usings:
            result["imports"] = [{"module": u} for u in usings]
        ns = re.search(r'namespace\s+([\w.]+)', content)
        if ns:
            result["namespace"] = ns.group(1)
        classes = re.findall(
            r'(?:public|internal|private)\s+(?:abstract|static|sealed\s+)?(?:class|interface)\s+(\w+)',
            content,
        )
        if classes:
            result["classes"] = [{"name": c} for c in classes]
    else:
        imports = re.findall(r'(?:import|include|require|use)\s+["\']?([^\s;"\']+)', content)
        if imports:
            result["imports"] = [{"module": i} for i in imports[:30]]
        classes = re.findall(r'(?:class|struct|interface|type)\s+(\w+)', content)
        if classes:
            result["classes"] = [{"name": c} for c in classes]
    return result


_EXTRACTORS = {
    "Python": _extract_python, "JavaScript": _extract_js_ts,
    "TypeScript": _extract_js_ts, "Java": _extract_java, "Go": _extract_go,
}

_CODE_LANG_MAP = {
    ".py": "Python", ".pyx": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin",
    ".go": "Go", ".rs": "Rust", ".cs": "C#", ".rb": "Ruby",
}


def extract_code_structure(repo_path: str, profile: dict) -> dict:
    """Extract code structure from T1 and T2 source files."""
    modules = {}
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    for file_info in profile.get("architecturally_relevant_files", []):
        tier = file_info["tier"]
        if tier == "T3":
            continue
        category = file_info["category"]
        if category not in ("source_code", "entry_point", "data_schema"):
            continue
        rel_path = file_info["path"]
        full_path = os.path.join(repo_path, rel_path)
        ext = os.path.splitext(rel_path)[1].lower()
        language = _CODE_LANG_MAP.get(ext)
        if not language or not os.path.isfile(full_path):
            stats["skipped"] += 1
            continue

        # Skip generated files
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                first_lines = f.read(500)
            if any(marker in first_lines.lower() for marker in
                   ("code generated", "auto-generated", "do not edit", "autogenerated")):
                stats["skipped"] += 1
                continue
        except (OSError, UnicodeDecodeError):
            stats["skipped"] += 1
            continue

        extractor = _EXTRACTORS.get(language)
        try:
            result = extractor(full_path, tier) if extractor else _extract_generic(full_path, language, tier)
        except Exception:
            logger.warning("AST extraction failed for %s", rel_path, exc_info=True)
            stats["errors"] += 1
            continue
        if result is None:
            stats["errors"] += 1
            continue

        result["tier"] = tier
        stats["processed"] += 1

        # Group files into modules by directory depth.  For Python
        # projects with src/<pkg>/<subpkg>/ layout, using 3 levels gives
        # separate modules for agents/, tools/, ingestion/ etc. instead
        # of collapsing everything into src/<pkg>.
        parts = Path(rel_path).parts
        if len(parts) >= 4:
            module_path = str(Path(parts[0]) / parts[1] / parts[2])
        elif len(parts) >= 3:
            module_path = str(Path(parts[0]) / parts[1])
        elif len(parts) >= 2:
            module_path = parts[0]
        else:
            module_path = "(root)"

        if module_path not in modules:
            modules[module_path] = {"path": module_path, "language": language, "files": []}
        modules[module_path]["files"].append({"path": rel_path, **result})

    # Enrich key_classes with collaborators (project-internal imports only)
    known_modules = set(modules.keys())
    for mod in modules.values():
        for file_info in mod["files"]:
            file_imports = file_info.get("imports", [])
            # Filter to project-internal imports: module path starts with a known module
            internal_names = []
            for imp in file_imports:
                imp_module = imp.get("module", "")
                top_level = imp_module.split(".")[0] if imp_module else ""
                if any(km.endswith(top_level) or top_level in km for km in known_modules if top_level):
                    # Use imported names if available, else the module name
                    names = imp.get("names", [])
                    if names:
                        internal_names.extend(names)
                    else:
                        internal_names.append(imp_module.split(".")[-1])
            if internal_names and file_info.get("classes"):
                for cls in file_info["classes"]:
                    if isinstance(cls, dict):
                        # Exclude the class's own bases (already tracked separately)
                        bases = set(cls.get("bases", []))
                        collaborators = [n for n in internal_names if n not in bases and n != cls.get("name")]
                        if collaborators:
                            cls["collaborators"] = sorted(set(collaborators))

    return {"modules": list(modules.values()), "stats": stats}


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH (from 05_build_dep_graph.py)
# ═══════════════════════════════════════════════════════════════════════════════

EXTERNAL_SDKS = {
    "stripe": "Stripe Payment API", "braintree": "Braintree Payment API",
    "paypal": "PayPal API", "twilio": "Twilio Messaging API",
    "sendgrid": "SendGrid Email API", "mailgun": "Mailgun Email API",
    "boto3": "AWS SDK", "botocore": "AWS SDK", "aws-sdk": "AWS SDK", "@aws-sdk": "AWS SDK",
    "google-cloud": "Google Cloud SDK", "@google-cloud": "Google Cloud SDK",
    "azure": "Azure SDK", "@azure": "Azure SDK",
    "auth0": "Auth0 Identity API", "okta": "Okta Identity API", "firebase": "Firebase",
    "datadog": "Datadog Monitoring", "sentry": "Sentry Error Tracking",
    "sentry-sdk": "Sentry Error Tracking", "newrelic": "New Relic Monitoring",
    "elasticsearch": "Elasticsearch", "algolia": "Algolia Search API",
    "minio": "MinIO Object Storage",
    "slack-sdk": "Slack API", "slack-bolt": "Slack API",
}

INFRA_IMAGES = {
    "postgres": ("database", "PostgreSQL"), "mysql": ("database", "MySQL"),
    "mariadb": ("database", "MariaDB"), "mongo": ("database", "MongoDB"),
    "redis": ("cache", "Redis"), "memcached": ("cache", "Memcached"),
    "rabbitmq": ("message_queue", "RabbitMQ"), "kafka": ("message_queue", "Apache Kafka"),
    "nats": ("message_queue", "NATS"), "mosquitto": ("message_queue", "Mosquitto MQTT"),
    "elasticsearch": ("search", "Elasticsearch"), "opensearch": ("search", "OpenSearch"),
    "minio": ("object_storage", "MinIO"),
    "nginx": ("reverse_proxy", "Nginx"), "traefik": ("reverse_proxy", "Traefik"),
    "haproxy": ("reverse_proxy", "HAProxy"), "envoy": ("reverse_proxy", "Envoy"),
    "vault": ("secrets_manager", "HashiCorp Vault"),
    "consul": ("service_discovery", "HashiCorp Consul"),
    "prometheus": ("monitoring", "Prometheus"), "grafana": ("monitoring", "Grafana"),
    "jaeger": ("tracing", "Jaeger"), "keycloak": ("identity", "Keycloak"),
    "localstack": ("cloud_emulator", "LocalStack"),
}

DB_ENV_PATTERNS = {
    "DATABASE_URL": "database", "DB_HOST": "database", "DB_URL": "database",
    "POSTGRES": "database", "PGHOST": "database", "MYSQL": "database",
    "MONGO": "database", "MONGODB": "database",
    "REDIS_URL": "cache", "REDIS_HOST": "cache",
    "RABBITMQ": "message_queue", "AMQP_URL": "message_queue",
    "KAFKA": "message_queue", "KAFKA_BOOTSTRAP": "message_queue",
    "ELASTICSEARCH": "search", "S3_BUCKET": "object_storage",
    "MINIO": "object_storage",
}


def _classify_docker_image(image_str):
    if not image_str:
        return None, None
    image_lower = image_str.lower().split(":")[0].split("/")[-1]
    for pattern, (infra_type, name) in INFRA_IMAGES.items():
        if pattern in image_lower:
            return infra_type, name
    return None, None


def build_dep_graph(code_structure: dict, manifests: dict) -> dict:
    """Build a module-level dependency graph."""
    nodes = {}
    edges = []
    seen_edges: set[tuple[str, str, str]] = set()
    clusters = defaultdict(set)

    # Step 1: docker-compose services
    topology = manifests.get("deployment_topology") or {}
    compose_services = topology.get("services", [])
    for svc in compose_services:
        name = svc["name"]
        image = svc.get("image_or_build", "")
        infra_type, infra_name = _classify_docker_image(image)
        if infra_type:
            nid = f"infra:{name}"
            nodes[nid] = {"id": nid, "type": infra_type, "name": infra_name or name,
                          "source": "docker-compose", "image": image}
        else:
            nid = f"mod:{name}"
            if nid not in nodes:
                nodes[nid] = {"id": nid, "type": "service", "name": name,
                              "source": "docker-compose",
                              "build_path": image if ("." in image or "/" in image) else None}
        for net in svc.get("networks", []):
            clusters[net].add(f"infra:{name}" if infra_type else f"mod:{name}")

    # Step 2: code modules
    for module in code_structure.get("modules", []):
        mod_path = module["path"]
        mod_name = mod_path.split("/")[-1] if "/" in mod_path else mod_path
        matched_id = None
        for nid, node in nodes.items():
            if nid.startswith("mod:"):
                build_path = node.get("build_path", "")
                if (build_path and mod_path in build_path) or mod_name == node["name"]:
                    matched_id = nid
                    break
        if matched_id:
            nodes[matched_id]["language"] = module["language"]
            nodes[matched_id]["code_path"] = mod_path
        else:
            nid = f"mod:{mod_name}"
            if nid not in nodes:
                nodes[nid] = {"id": nid, "type": "service", "name": mod_name,
                              "language": module["language"], "source": "code_analysis",
                              "code_path": mod_path}

    # evidence_strength values:
    #   "strong" — env var, package dep, code import, or depends_on + corroborating evidence
    #   "weak"   — depends_on only (startup ordering, may not indicate runtime dependency)
    depends_on_edge_indices: list[int] = []  # track for post-processing

    # Step 3: depends_on edges (initially marked "weak", upgraded to "strong" if corroborated)
    for svc in compose_services:
        svc_name = svc["name"]
        svc_id = f"mod:{svc_name}" if f"mod:{svc_name}" in nodes else None
        if not svc_id:
            continue
        for dep_name in svc.get("depends_on", []):
            dep_id = None
            for nid in nodes:
                if nid.endswith(f":{dep_name}"):
                    dep_id = nid
                    break
            if dep_id:
                dep_type = nodes[dep_id]["type"]
                edge_type = ("data_access" if dep_type in ("database", "cache") else
                             "messaging" if dep_type == "message_queue" else
                             "infrastructure_dependency")
                key = (svc_id, dep_id, edge_type)
                if key not in seen_edges:
                    seen_edges.add(key)
                    depends_on_edge_indices.append(len(edges))
                    edges.append({"from": svc_id, "to": dep_id, "type": edge_type,
                                  "evidence": f"docker-compose depends_on: {dep_name}",
                                  "evidence_strength": "weak"})

    # Step 4: env var edges
    for svc in compose_services:
        svc_id = f"mod:{svc['name']}"
        if svc_id not in nodes:
            continue
        for env_key in svc.get("environment_keys", []):
            env_upper = env_key.upper()
            for pattern, edge_type in DB_ENV_PATTERNS.items():
                if pattern in env_upper:
                    for nid, node in nodes.items():
                        if nid.startswith("infra:") and node["type"] == edge_type:
                            key = (svc_id, nid, "data_access")
                            if key not in seen_edges:
                                seen_edges.add(key)
                                edges.append({"from": svc_id, "to": nid, "type": "data_access",
                                              "evidence": f"env var: {env_key}",
                                              "evidence_strength": "strong"})
                            break

    # Step 5: external SDK edges
    for pkg_info in manifests.get("package_dependencies", []):
        module_path = pkg_info.get("module", "(root)")
        svc_id = None
        for nid, node in nodes.items():
            if nid.startswith("mod:"):
                if node.get("code_path") == module_path or node["name"] in module_path:
                    svc_id = nid
                    break
        if not svc_id:
            mod_nodes = [nid for nid in nodes if nid.startswith("mod:")]
            svc_id = mod_nodes[0] if mod_nodes else None
        if not svc_id:
            continue
        for dep in pkg_info.get("runtime_deps", []):
            dep_lower = dep.lower()
            for sdk_pattern, ext_name in EXTERNAL_SDKS.items():
                if sdk_pattern in dep_lower:
                    ext_id = f"ext:{sdk_pattern}"
                    if ext_id not in nodes:
                        nodes[ext_id] = {"id": ext_id, "type": "external_service",
                                         "name": ext_name, "source": f"package dependency: {dep}"}
                    key = (svc_id, ext_id, "external_integration")
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append({"from": svc_id, "to": ext_id, "type": "external_integration",
                                      "evidence": f"package: {dep} in {pkg_info['source_file']}",
                                      "evidence_strength": "strong"})
                    break

    # Step 6: cross-module import edges
    mod_node_by_path = {node["code_path"]: nid for nid, node in nodes.items()
                        if nid.startswith("mod:") and node.get("code_path")}
    for module in code_structure.get("modules", []):
        mod_path = module["path"]
        src_id = mod_node_by_path.get(mod_path)
        if not src_id:
            mod_name = mod_path.split("/")[-1]
            src_id = f"mod:{mod_name}" if f"mod:{mod_name}" in nodes else None
        if not src_id:
            continue
        for file_info in module.get("files", []):
            for imp in file_info.get("imports", []):
                imp_module = imp.get("module", "")
                for other_path, other_id in mod_node_by_path.items():
                    if other_id == src_id:
                        continue
                    other_name = other_path.split("/")[-1]
                    if other_name in imp_module or other_path.replace("/", ".") in imp_module:
                        key = (src_id, other_id, "api_call")
                        if key not in seen_edges:
                            seen_edges.add(key)
                            edges.append({"from": src_id, "to": other_id, "type": "api_call",
                                          "evidence": f"import: {imp_module} in {file_info['path']}",
                                          "evidence_strength": "strong"})
                        break

    # Step 7: upgrade depends_on edges with corroborating env var evidence
    env_var_pairs = {(e["from"], e["to"]) for e in edges if "env var" in e.get("evidence", "")}
    for idx in depends_on_edge_indices:
        edge = edges[idx]
        if (edge["from"], edge["to"]) in env_var_pairs:
            edge["evidence_strength"] = "strong"

    # Step 8: clusters
    cluster_list = [{"name": name, "members": sorted(members)} for name, members in clusters.items()]

    # Edges are already deduplicated via seen_edges during insertion
    return {"nodes": list(nodes.values()), "edges": edges, "clusters": cluster_list}
