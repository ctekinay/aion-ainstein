"""Repository architecture analysis toolkit.

Provides deterministic extraction of architectural information from
codebases — zero LLM tokens. Logic ported from draft scripts 01, 02, 06
in docs/.local/archimate-repo-skill-upgrade/.
"""

import json
import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CLONE_SIZE_MB = 1024  # Hard abort if cloned repo exceeds this

# ── Skip patterns ─────────────────────────────────────────────────────────────

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".env", "vendor", "dist", "build", "target", ".next", ".nuxt",
    ".cache", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "coverage", ".coverage", "htmlcov", ".idea", ".vscode",
    ".terraform", ".serverless", "egg-info", ".eggs",
    "bower_components", "jspm_packages", ".parcel-cache",
    ".turbo", ".vercel", ".output", "out",
    "archive", "temp",
}

SKIP_EXTENSIONS = {
    ".lock", ".sum", ".min.js", ".min.css", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp", ".tiff",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z", ".jar", ".war",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".class", ".o", ".so", ".dylib", ".dll", ".exe",
    ".DS_Store", ".gitkeep",
}

# ── Language detection ────────────────────────────────────────────────────────

LANG_MAP = {
    ".py": "Python", ".pyx": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#", ".fs": "F#", ".vb": "VB.NET",
    ".rb": "Ruby", ".erb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".clj": "Clojure", ".cljs": "Clojure",
    ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".r": "R", ".R": "R",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".tf": "Terraform", ".tfvars": "Terraform",
    ".sql": "SQL",
    ".proto": "Protobuf",
    ".graphql": "GraphQL", ".gql": "GraphQL",
}

# ── Framework detection markers ───────────────────────────────────────────────

FRAMEWORK_MARKERS = {
    "requirements.txt": ["fastapi", "django", "flask", "tornado", "starlette",
                          "celery", "airflow", "scrapy", "pytest"],
    "pyproject.toml": ["fastapi", "django", "flask", "tornado", "starlette",
                        "celery", "airflow", "pydantic"],
    "setup.py": ["fastapi", "django", "flask"],
    "Pipfile": ["fastapi", "django", "flask"],
    "package.json": ["react", "next", "vue", "nuxt", "angular", "svelte",
                      "express", "nestjs", "fastify", "koa", "hapi",
                      "electron", "gatsby", "remix"],
    "pom.xml": ["spring", "quarkus", "micronaut", "vert.x"],
    "build.gradle": ["spring", "quarkus", "micronaut"],
    "build.gradle.kts": ["spring", "quarkus", "micronaut"],
    "go.mod": ["gin", "echo", "fiber", "chi", "gorilla"],
    "Cargo.toml": ["actix", "axum", "rocket", "warp", "tokio"],
    "Gemfile": ["rails", "sinatra", "hanami"],
}

# ── Database driver detection ─────────────────────────────────────────────────

DB_DRIVERS = {
    "psycopg2": "PostgreSQL", "psycopg": "PostgreSQL", "asyncpg": "PostgreSQL",
    "pymysql": "MySQL", "mysql-connector-python": "MySQL", "aiomysql": "MySQL",
    "pymongo": "MongoDB", "motor": "MongoDB",
    "redis": "Redis", "aioredis": "Redis",
    "sqlalchemy": "SQL (generic)", "alembic": "SQL (generic)",
    "prisma": "Prisma", "tortoise-orm": "SQL (generic)",
    "elasticsearch": "Elasticsearch", "opensearch-py": "OpenSearch",
    "cassandra-driver": "Cassandra", "neo4j": "Neo4j",
    "pg": "PostgreSQL", "postgres": "PostgreSQL",
    "mysql2": "MySQL", "mongoose": "MongoDB", "mongodb": "MongoDB",
    "ioredis": "Redis",
    "typeorm": "SQL (generic)", "sequelize": "SQL (generic)", "knex": "SQL (generic)",
    "@prisma/client": "Prisma",
    "better-sqlite3": "SQLite", "sqlite3": "SQLite",
    "postgresql": "PostgreSQL", "mysql-connector-java": "MySQL",
    "spring-data-mongodb": "MongoDB", "spring-data-redis": "Redis",
    "spring-data-jpa": "SQL (generic)", "hibernate": "SQL (generic)",
    "github.com/lib/pq": "PostgreSQL", "github.com/jackc/pgx": "PostgreSQL",
    "github.com/go-sql-driver/mysql": "MySQL",
    "go.mongodb.org/mongo-driver": "MongoDB",
    "github.com/go-redis/redis": "Redis",
    "gorm.io/gorm": "SQL (generic)",
}

# ── T1 file patterns (architecturally critical) ──────────────────────────────

T1_EXACT_NAMES = {
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "Dockerfile", "Makefile",
    "README.md", "README.rst", "README.txt", "README",
    "ARCHITECTURE.md", "DESIGN.md",
    ".github/workflows", ".gitlab-ci.yml", "Jenkinsfile",
    "bitbucket-pipelines.yml", ".circleci/config.yml",
    "serverless.yml", "serverless.yaml",
    "fly.toml", "railway.json", "render.yaml", "app.yaml",
    "nginx.conf", "Caddyfile", "traefik.yml",
}

T1_PATTERNS = [
    re.compile(r"Dockerfile(\..+)?$"),
    re.compile(r"docker-compose[\w.-]*\.(yml|yaml)$"),
    re.compile(r"\.github/workflows/.+\.(yml|yaml)$"),
    re.compile(r"(openapi|swagger)\.(ya?ml|json)$", re.I),
    re.compile(r".*\.proto$"),
    re.compile(r".*\.graphql$"),
    re.compile(r".*schema.*\.(graphql|gql)$", re.I),
    re.compile(r".*\.tf$"),
    re.compile(r".*\.tfvars$"),
    re.compile(r"(helm|charts?|k8s|kubernetes)/.+\.(ya?ml)$"),
    re.compile(r".*/migrations?/.*\.(sql|py|rb|ts|js)$"),
    re.compile(r".*/models?/[^/]+\.(py|java|kt|go|rs|ts|js|rb|cs)$"),
    re.compile(r".*/schema(s)?/[^/]+\.(py|java|kt|go|rs|ts|js|rb|cs)$"),
    re.compile(r".*/entities?/[^/]+\.(py|java|kt|go|rs|ts|js|rb|cs)$"),
    re.compile(r".*\.prisma$"),
    re.compile(r".*ADR[-_]\d+.*\.md$", re.I),
    re.compile(r".*adr/.*\.md$", re.I),
]

T1_ENTRY_NAMES = {
    "main.py", "app.py", "server.py", "wsgi.py", "asgi.py", "manage.py",
    "main.go", "cmd/main.go",
    "main.rs", "lib.rs",
    "index.ts", "index.js", "app.ts", "app.js", "server.ts", "server.js",
    "Main.java", "Application.java",
    "Program.cs", "Startup.cs",
    "config.ru",
}

T3_DIRS = {
    "test", "tests", "__tests__", "spec", "specs", "test_data", "testdata",
    "fixtures", "mocks", "__mocks__", "stubs",
    "docs", "doc", "documentation",
    "examples", "example", "samples", "sample", "demo", "demos",
    "scripts", "tools", "util", "utils", "helpers",
    "static", "public", "assets", "images", "img", "fonts", "icons",
    "locales", "i18n", "l10n", "translations",
    "views", "templates",
}


# ── Helper functions ──────────────────────────────────────────────────────────

_SKIP_DIR_PREFIXES = ("venv", ".venv", "env", ".env", "egg-info")


def _should_skip_dir(dirname):
    if dirname in SKIP_DIRS or dirname.startswith("."):
        return True
    # Catch variant venv names like venv312, .venv3, env-py3, *.egg-info
    lower = dirname.lower()
    return any(lower.startswith(prefix) for prefix in _SKIP_DIR_PREFIXES) or lower.endswith(".egg-info")


def _should_skip_file(filepath, ext):
    if ext in SKIP_EXTENSIONS:
        return True
    name = os.path.basename(filepath)
    if name.startswith(".") and name not in {".env.example", ".env.template"}:
        return True
    return False


def _classify_tier(rel_path, filename):
    if filename in T1_EXACT_NAMES or filename in T1_ENTRY_NAMES:
        return "T1"
    for pattern in T1_PATTERNS:
        if pattern.search(rel_path):
            return "T1"
    parts = Path(rel_path).parts
    for part in parts:
        if part.lower() in T3_DIRS:
            return "T3"
    return "T2"


def _categorize_file(rel_path, filename, ext):
    lower = filename.lower()
    lower_path = rel_path.lower()

    if "docker-compose" in lower or "compose" in lower:
        return "deployment"
    if "dockerfile" in lower:
        return "containerization"
    if ext in (".tf", ".tfvars"):
        return "iac"
    if "openapi" in lower or "swagger" in lower:
        return "api_definition"
    if ext == ".proto":
        return "api_definition"
    if ext in (".graphql", ".gql"):
        return "api_definition"
    if "migration" in lower_path and ext in (".sql", ".py", ".rb", ".ts", ".js"):
        return "data_schema"
    if any(d in lower_path for d in ("models/", "model/", "entities/", "entity/", "schema/")):
        return "data_schema"
    if ext == ".prisma":
        return "data_schema"
    if "adr" in lower_path:
        return "architecture_decision"
    if lower in ("readme.md", "readme.rst", "architecture.md", "design.md"):
        return "documentation"
    if ".github/workflows" in rel_path or lower in (".gitlab-ci.yml", "jenkinsfile"):
        return "ci_cd"
    if any(d in lower_path for d in ("helm/", "charts/", "k8s/", "kubernetes/")):
        return "orchestration"
    if filename in T1_ENTRY_NAMES:
        return "entry_point"
    if ext in LANG_MAP:
        return "source_code"
    return "other"


# ── Clone ─────────────────────────────────────────────────────────────────────

def _extract_branch_from_url(url: str) -> tuple[str, str | None]:
    """Strip /tree/<branch> or /blob/<branch> from GitHub web URLs.

    Returns (clean_url, branch_or_None).  Only /tree/ URLs yield a branch
    because /blob/ URLs mix branch name with file path (e.g.,
    /blob/main/README.md) — can't reliably separate them.

    Example: "https://github.com/Org/repo/tree/feature/foo" → ("https://github.com/Org/repo", "feature/foo")
    """
    for marker in ("/tree/", "/blob/"):
        idx = url.find(marker)
        if idx != -1:
            remainder = url[idx + len(marker):].rstrip("/")
            # /blob/ URLs mix branch + file path — only extract branch from /tree/
            branch = remainder if marker == "/tree/" and remainder else None
            return url[:idx], branch
    return url, None


def _extract_repo_identity(url: str) -> tuple[str, str]:
    """Extract (owner/repo, repo_name) from a git URL.

    Handles https://github.com/owner/repo.git, git@github.com:owner/repo.git,
    and web URLs with /tree/<branch> or /blob/<branch>.
    """
    # Strip branch path before identity extraction
    cleaned, _ = _extract_branch_from_url(url)
    cleaned = cleaned.rstrip("/").removesuffix(".git")
    # git@github.com:owner/repo → split on ":"
    if cleaned.startswith("git@"):
        parts = cleaned.split(":")[-1].split("/")
    else:
        parts = cleaned.split("/")
    repo_name = parts[-1] if parts else "unknown"
    owner = parts[-2] if len(parts) >= 2 else "unknown"
    return f"{owner}/{repo_name}", repo_name


def _git_metadata(repo_path: str) -> dict:
    """Extract branch, commit SHA, and default branch from a git repo.

    Returns dict with branch, commit_sha, default_branch (all nullable).
    """
    meta = {"branch": None, "commit_sha": None, "default_branch": None}
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return meta
    try:
        sha = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if sha.returncode == 0:
            meta["commit_sha"] = sha.stdout.strip()
    except Exception:
        pass
    try:
        br = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if br.returncode == 0 and br.stdout.strip() != "HEAD":
            meta["branch"] = br.stdout.strip()
    except Exception:
        pass
    try:
        ref = subprocess.run(
            ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if ref.returncode == 0:
            # refs/remotes/origin/main → main
            meta["default_branch"] = ref.stdout.strip().split("/")[-1]
    except Exception:
        pass
    return meta


def git_diff_stats(repo_path: str, base_branch: str) -> dict:
    """Get file-level diff stats between base_branch and HEAD.

    Returns {"new": [...], "modified": [...], "deleted": [...]}.
    Returns empty dict on failure (shallow clone, missing base, non-git dir).
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {}
    except Exception:
        return {}

    new, modified, deleted = [], [], []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts[0].strip(), parts[1].strip()
        if status == "A":
            new.append(path)
        elif status == "M":
            modified.append(path)
        elif status == "D":
            deleted.append(path)
        # R (rename), C (copy) — treat as modified
        elif status.startswith(("R", "C")):
            modified.append(path)
    return {"new": new, "modified": modified, "deleted": deleted}


def clone_repo(url_or_path: str) -> dict:
    """Clone a repo or validate a local path.

    Returns dict with repo_path, repo_name, clone_size_mb, repo_url,
    branch, commit_sha, and default_branch.
    """
    # Reject unsupported URL schemes — only https:// and git@ allowed
    if url_or_path.startswith(("file://", "ssh://", "ftp://", "http://")):
        return {"error": "Unsupported URL scheme. Use https:// or git@ URLs."}

    # Local path
    if not url_or_path.startswith(("https://", "git@")):
        resolved = os.path.abspath(url_or_path)
        if not os.path.isdir(resolved):
            return {"error": f"Directory not found: {resolved}"}
        file_count = sum(1 for _ in Path(resolved).rglob("*") if _.is_file())
        if file_count == 0:
            return {"error": f"Directory appears empty: {resolved}"}
        git_meta = _git_metadata(resolved)
        return {
            "repo_path": resolved,
            "repo_name": os.path.basename(resolved),
            "clone_size_mb": 0,
            "is_local": True,
            "repo_url": url_or_path,
            **git_meta,
        }

    # Extract branch from GitHub web URLs (/tree/<branch>, /blob/<branch>)
    clone_url, branch = _extract_branch_from_url(url_or_path)
    # Ensure clone URL ends with .git for git clone
    if not clone_url.endswith(".git"):
        clone_url_git = clone_url + ".git"
    else:
        clone_url_git = clone_url

    # Extract repo identity — use owner/name to avoid collisions
    identity, name = _extract_repo_identity(url_or_path)
    target = f"/tmp/rta/{identity}"

    # Check for stale clone — verify the remote matches
    if os.path.isdir(os.path.join(target, ".git")):
        try:
            result = subprocess.run(
                ["git", "-C", target, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            cached_url = result.stdout.strip().rstrip("/").removesuffix(".git")
            incoming_clean = clone_url.rstrip("/").removesuffix(".git")
            if cached_url == incoming_clean:
                logger.info("Repository already cloned at %s", target)
                git_meta = _git_metadata(target)
                # Use URL-extracted branch as fallback if detached HEAD
                if not git_meta["branch"] and branch:
                    git_meta["branch"] = branch
                return {
                    "repo_path": target,
                    "repo_name": name,
                    "clone_size_mb": _dir_size_mb(target),
                    "is_local": False,
                    "repo_url": url_or_path,
                    **git_meta,
                }
            else:
                logger.warning("Stale clone at %s (remote mismatch), re-cloning", target)
                import shutil
                shutil.rmtree(target, ignore_errors=True)
        except Exception:
            pass

    os.makedirs(os.path.dirname(target), exist_ok=True)
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [clone_url_git, target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"error": f"Git clone failed: {result.stderr.strip()[:200]}"}
    except subprocess.TimeoutExpired:
        return {"error": "Git clone timed out after 120 seconds"}
    except FileNotFoundError:
        return {"error": "git command not found"}

    size_mb = _dir_size_mb(target)
    if size_mb > MAX_CLONE_SIZE_MB:
        import shutil
        shutil.rmtree(target, ignore_errors=True)
        return {
            "error": (
                f"Cloned repository is {size_mb:.0f} MB, exceeding the {MAX_CLONE_SIZE_MB} MB limit. "
                f"Clone it locally and point to a specific subdirectory instead."
            ),
        }

    git_meta = _git_metadata(target)
    # Use URL-extracted branch as fallback if detached HEAD
    if not git_meta["branch"] and branch:
        git_meta["branch"] = branch
    return {
        "repo_path": target,
        "repo_name": name,
        "clone_size_mb": round(size_mb, 1),
        "is_local": False,
        "repo_url": url_or_path,
        **git_meta,
    }


def _dir_size_mb(path: str) -> float:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total / (1024 * 1024)


# ── Profile ───────────────────────────────────────────────────────────────────

def profile_repo(repo_path: str) -> dict:
    """Produce a compact structural profile without reading file contents."""
    repo_path = os.path.abspath(repo_path)
    repo_name = os.path.basename(repo_path)

    file_index = {}
    total_files = 0
    total_dirs = 0
    total_size = 0
    lang_stats = Counter()
    lang_bytes = Counter()

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
        total_dirs += len(dirs)

        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_path)
            ext = os.path.splitext(filename)[1].lower()

            if _should_skip_file(rel_path, ext):
                continue

            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue

            total_files += 1
            total_size += size

            language = LANG_MAP.get(ext)
            if language:
                lang_stats[language] += 1
                lang_bytes[language] += size

            tier = _classify_tier(rel_path, filename)
            category = _categorize_file(rel_path, filename, ext)

            file_index[rel_path] = {
                "filename": filename, "ext": ext, "size": size,
                "language": language, "tier": tier, "category": category,
            }

    modules = _detect_modules(repo_path, file_index)
    structure_type = _detect_structure_type(modules, file_index)
    frameworks = _detect_frameworks(repo_path, file_index)
    databases = _detect_databases(repo_path, file_index)

    containerization = []
    if any("dockerfile" in info["filename"].lower() for info in file_index.values()):
        containerization.append("Docker")
    if any("compose" in info["filename"].lower() for info in file_index.values()):
        containerization.append("docker-compose")
    if any("helm/" in p.lower() or "charts/" in p.lower() for p in file_index):
        containerization.append("Helm")
    if any("k8s/" in p.lower() or "kubernetes/" in p.lower() for p in file_index):
        containerization.append("Kubernetes")

    ci_cd = []
    if any(".github/workflows" in p for p in file_index):
        ci_cd.append("GitHub Actions")
    if any(file_index[p]["filename"] == ".gitlab-ci.yml" for p in file_index):
        ci_cd.append("GitLab CI")
    if any(file_index[p]["filename"].lower() == "jenkinsfile" for p in file_index):
        ci_cd.append("Jenkins")

    iac = []
    if any(p.endswith(".tf") for p in file_index):
        iac.append("Terraform")
    if any("helm/" in p.lower() or "charts/" in p.lower() for p in file_index):
        iac.append("Helm")

    pkg_map = {
        "requirements.txt": "pip", "pyproject.toml": "pip", "Pipfile": "pipenv",
        "package.json": "npm", "yarn.lock": "yarn", "pnpm-lock.yaml": "pnpm",
        "go.mod": "go modules", "Cargo.toml": "cargo",
        "pom.xml": "maven", "build.gradle": "gradle", "Gemfile": "bundler",
    }
    pkg_managers = []
    for info in file_index.values():
        if info["filename"] in pkg_map:
            pm = pkg_map[info["filename"]]
            if pm not in pkg_managers:
                pkg_managers.append(pm)

    languages = [
        {"language": lang, "file_count": count, "total_bytes": lang_bytes[lang]}
        for lang, count in lang_stats.most_common()
    ]

    arch_files = [
        {"path": p, "category": info["category"], "size_bytes": info["size"], "tier": info["tier"]}
        for p, info in sorted(file_index.items())
        if info["tier"] in ("T1", "T2")
    ]
    arch_files.sort(key=lambda f: (0 if f["tier"] == "T1" else 1, f["category"], f["path"]))

    return {
        "repo_name": repo_name,
        "total_files": total_files,
        "total_dirs": total_dirs,
        "total_size_bytes": total_size,
        "structure_type": structure_type,
        "tech_stack": {
            "languages": languages,
            "frameworks": frameworks,
            "package_managers": pkg_managers,
            "containerization": containerization,
            "ci_cd": ci_cd,
            "iac": iac,
            "databases": databases,
        },
        "modules": modules,
        "architecturally_relevant_files": arch_files,
        "file_tier_counts": {
            "T1": sum(1 for info in file_index.values() if info["tier"] == "T1"),
            "T2": sum(1 for info in file_index.values() if info["tier"] == "T2"),
            "T3": sum(1 for info in file_index.values() if info["tier"] == "T3"),
        },
    }


def _word_boundary_match(needle: str, haystack: str) -> bool:
    """Check if needle appears as a whole word/package name in haystack.

    Uses word boundary regex to avoid false positives like 'pg' matching 'upgrading'.
    """
    return bool(re.search(r'(?:^|[\s"\',=\[\]{}()])' + re.escape(needle) + r'(?:$|[\s"\',=\[\]{}()><=!;])', haystack))


def _detect_frameworks(repo_path, file_index):
    frameworks = set()
    for rel_path, info in file_index.items():
        if info["filename"] not in FRAMEWORK_MARKERS:
            continue
        full_path = os.path.join(repo_path, rel_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().lower()
        except (OSError, UnicodeDecodeError):
            continue
        for marker in FRAMEWORK_MARKERS[info["filename"]]:
            if _word_boundary_match(marker.lower(), content):
                frameworks.add(marker)
    return sorted(frameworks)


def _detect_databases(repo_path, file_index):
    databases = set()
    manifest_names = {
        "requirements.txt", "pyproject.toml", "Pipfile",
        "package.json", "go.mod", "Cargo.toml",
        "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    }
    for rel_path, info in file_index.items():
        if info["filename"] not in manifest_names:
            continue
        full_path = os.path.join(repo_path, rel_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().lower()
        except (OSError, UnicodeDecodeError):
            continue
        for driver, db_name in DB_DRIVERS.items():
            if _word_boundary_match(driver.lower(), content):
                databases.add(db_name)
    return sorted(databases)


def _detect_structure_type(modules, file_index):
    top_dirs = set()
    for rel_path in file_index:
        parts = Path(rel_path).parts
        if len(parts) > 1:
            top_dirs.add(parts[0])

    monorepo_dirs = {"services", "packages", "apps", "libs", "modules", "projects"}
    if top_dirs & monorepo_dirs:
        return "monorepo"

    dockerfile_dirs = set()
    for rel_path, info in file_index.items():
        if "dockerfile" in info["filename"].lower():
            parent = str(Path(rel_path).parent)
            if parent != ".":
                dockerfile_dirs.add(parent)
    if len(dockerfile_dirs) >= 2:
        return "monorepo"

    lib_markers = {"setup.py", "pyproject.toml", "setup.cfg", "Cargo.toml",
                   "build.gradle", "pom.xml"}
    has_lib_marker = any(info["filename"] in lib_markers for info in file_index.values())
    has_src = "src" in top_dirs
    has_no_dockerfile = not any("dockerfile" in info["filename"].lower() for info in file_index.values())
    if has_lib_marker and has_src and has_no_dockerfile:
        return "library"

    has_dockerfile = any("dockerfile" in info["filename"].lower() for info in file_index.values())
    has_compose = any("compose" in info["filename"].lower() for info in file_index.values())
    if has_dockerfile or has_compose:
        return "single-service"

    return "unknown"


def _detect_modules(repo_path, file_index):
    modules = []
    manifest_names = {
        "Dockerfile", "package.json", "requirements.txt", "pyproject.toml",
        "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Gemfile",
        "setup.py", "setup.cfg",
    }

    dir_files = defaultdict(list)
    for rel_path, info in file_index.items():
        # 3-level grouping matching repo_extractors.py — subpackages
        # like src/aion/agents/ become separate modules instead of
        # collapsing into src/aion.
        parts = Path(rel_path).parts
        if len(parts) >= 4:
            mod_path = str(Path(parts[0]) / parts[1] / parts[2])
        elif len(parts) >= 3:
            mod_path = str(Path(parts[0]) / parts[1])
        elif len(parts) >= 2:
            mod_path = parts[0]
        else:
            mod_path = "(root)"
        dir_files[mod_path].append((rel_path, info))

    service_parents = {"services", "packages", "apps", "cmd", "internal"}
    for parent_dir in service_parents:
        parent_path = os.path.join(repo_path, parent_dir)
        if os.path.isdir(parent_path):
            for child in os.listdir(parent_path):
                child_path = os.path.join(parent_path, child)
                if os.path.isdir(child_path) and not _should_skip_dir(child):
                    mod_path = f"{parent_dir}/{child}"
                    if mod_path not in dir_files:
                        for rel_path, info in file_index.items():
                            if rel_path.startswith(mod_path + "/"):
                                dir_files[mod_path].append((rel_path, info))

    for mod_path, files in sorted(dir_files.items()):
        if mod_path == "(root)" or len(files) < 2:
            continue
        filenames = {info["filename"] for _, info in files}
        languages = Counter(info.get("language") for _, info in files if info.get("language"))
        if not (filenames & manifest_names) and not languages:
            continue

        dominant_lang = languages.most_common(1)[0][0] if languages else None
        modules.append({
            "path": mod_path,
            "dominant_language": dominant_lang,
            "file_count": len(files),
            "has_dockerfile": any("dockerfile" in fn.lower() for fn in filenames),
            "has_api_definition": any(info["category"] == "api_definition" for _, info in files),
            "has_db_schema": any(info["category"] == "data_schema" for _, info in files),
            "entry_points": [info["filename"] for _, info in files if info["filename"] in T1_ENTRY_NAMES],
        })

    return modules


# ── Merge ─────────────────────────────────────────────────────────────────────

# Bump when the architecture_notes schema changes. If the template evolves
# and this code doesn't update in lockstep, the version creates false confidence.
TEMPLATE_VERSION = "1.0"


def _build_provenance(clone_result: dict | None) -> dict:
    """Build the provenance audit-trail block.

    Identity fields are stubbed as null — requires GitHub auth (future work).
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cr = clone_result or {}
    return {
        "identity": {
            "display_name": None,
            "business_email": None,
            "github_handle": None,
            "github_id": None,
            "organization": None,
            "team": None,
        },
        "temporal": {
            "access_time": now,
            "generated_at": now,
            "timezone": "UTC",
        },
        "context": {
            "trigger": "repo-analysis-agent",
            "tool": "ainstein",
            "tool_version": TEMPLATE_VERSION,
            "repo_url": cr.get("repo_url"),
            "commit_sha": cr.get("commit_sha"),
        },
    }


def _build_meta(profile: dict, clone_result: dict | None, base_branch: str | None) -> dict:
    """Build the meta identity block."""
    cr = clone_result or {}
    return {
        "repo_name": profile.get("repo_name", "unknown"),
        "branch": cr.get("branch"),
        "base_branch": base_branch,
        "analyzer_version": TEMPLATE_VERSION,
    }


def _infer_component_role(component: dict) -> str:
    """Best-effort role inference from component structure and name.

    This is a hint, not a binding contract. The LLM re-interprets the role
    during ArchiMate generation and can override misclassifications.
    """
    name_lower = component.get("name", "").lower()
    # Has API endpoints, route registrations, or web framework decorators → api
    if component.get("api_endpoints"):
        return "api"
    for kf in component.get("key_functions", []):
        if not isinstance(kf, dict):
            continue
        if kf.get("type") == "route":
            return "api"
        # Decorated functions with web framework route decorators
        for dec in kf.get("decorators", []):
            if any(fw in dec for fw in (".get(", ".post(", ".put(", ".delete(", ".patch(",
                                        ".route(", ".api_route(", "Router()")):
                return "api"
    if any(kw in name_lower for kw in ("worker", "celery", "consumer")):
        return "worker"
    if any(kw in name_lower for kw in ("scheduler", "cron", "periodic")):
        return "scheduler"
    if any(kw in name_lower for kw in ("gateway", "proxy", "ingress")):
        return "gateway"
    return "service"


def _build_edges(dep_graph: dict) -> list[dict]:
    """Restructure dep_graph edges into top-level directed edge list.

    Directionality: from = caller/dependent, to = target/dependency.
    """
    edges = []
    for edge in dep_graph.get("edges", []):
        edges.append({
            "from": edge["from"],
            "to": edge["to"],
            "relation": edge.get("type", "calls"),
            "evidence": edge.get("evidence", ""),
            "evidence_strength": edge.get("evidence_strength", "weak"),
        })
    return edges


def _build_diff(diff_stats: dict, components: list[dict],
                base_branch: str | None) -> tuple[dict, set[str]]:
    """Build diff block and identify changed component IDs.

    Returns (diff_block, changed_component_ids). Does not mutate inputs.
    """
    all_changed = set(
        diff_stats.get("new", []) +
        diff_stats.get("modified", []) +
        diff_stats.get("deleted", [])
    )
    changed_ids = set()
    for comp in components:
        comp_path = comp.get("path") or ""
        if comp_path and any(f.startswith(comp_path) for f in all_changed):
            changed_ids.add(comp["id"])
    return {
        "base_branch": base_branch,
        "new_files": len(diff_stats.get("new", [])),
        "modified_files": len(diff_stats.get("modified", [])),
        "deleted_files": len(diff_stats.get("deleted", [])),
        "changed_components": sorted(changed_ids),
    }, changed_ids


def _build_config_surface(infrastructure_nodes: list[dict],
                           manifests: dict) -> dict[str, list[str]]:
    """Map infrastructure IDs to their configuration key names.

    Returns {infra_id: [key_names]}. Strips values from key=value pairs —
    only key names, NEVER values (security: prevents leaking secrets).
    """
    # Build a lookup: compose service name → environment_keys
    svc_env = {}
    topo = manifests.get("deployment_topology", {})
    for svc in topo.get("services", []):
        svc_name = svc.get("name", "")
        raw_keys = svc.get("environment_keys", [])
        # Strip values: "DATABASE_URL=postgres://..." → "DATABASE_URL"
        clean_keys = [k.split("=", 1)[0].strip() for k in raw_keys if k]
        if clean_keys:
            svc_env[svc_name.lower()] = clean_keys

    result = {}
    for node in infrastructure_nodes:
        nid = node["id"]
        infra_name = node.get("name", "").lower()
        # Match infrastructure node to compose services that serve it
        # (via serves list or name similarity)
        for svc_name, keys in svc_env.items():
            if infra_name in svc_name or svc_name in infra_name:
                result[nid] = keys
                break
    return result


def merge_architecture_notes(profile: dict, manifests: dict,
                             code_structure: dict, dep_graph: dict,
                             *, clone_result: dict | None = None,
                             base_branch: str | None = None,
                             diff_stats: dict | None = None) -> dict:
    """Merge all extraction outputs into a single v1.0 architecture_notes."""
    tech_parts = []
    for lang in profile.get("tech_stack", {}).get("languages", [])[:3]:
        tech_parts.append(lang["language"])
    for fw in profile.get("tech_stack", {}).get("frameworks", [])[:3]:
        tech_parts.append(fw)
    for db in profile.get("tech_stack", {}).get("databases", []):
        tech_parts.append(db)
    for ct in profile.get("tech_stack", {}).get("containerization", [])[:2]:
        tech_parts.append(ct)
    for iac_tool in profile.get("tech_stack", {}).get("iac", [])[:2]:
        tech_parts.append(iac_tool)

    nodes = dep_graph.get("nodes", [])
    mod_count = sum(1 for n in nodes if n["id"].startswith("mod:"))
    infra_count = sum(1 for n in nodes if n["id"].startswith("infra:"))
    ext_count = sum(1 for n in nodes if n["id"].startswith("ext:"))

    summary = {
        "repo_name": profile.get("repo_name", "unknown"),
        "structure_type": profile.get("structure_type", "unknown"),
        "tech_stack": tech_parts,
        "total_components": mod_count,
        "total_infrastructure": infra_count,
        "total_external": ext_count,
        "total_files_analyzed": (profile.get("file_tier_counts", {}).get("T1", 0) +
                                 profile.get("file_tier_counts", {}).get("T2", 0)),
        "total_edges": len(dep_graph.get("edges", [])),
    }

    # Build component index
    components = {}
    infrastructure = {}
    external_services = {}

    for node in nodes:
        nid = node["id"]
        if nid.startswith("mod:"):
            components[nid] = {
                "id": nid, "name": node.get("name", nid.split(":")[-1]),
                "type": node.get("type", "service"),
                "language": node.get("language"),
                "path": node.get("code_path") or node.get("build_path"),
                "source": node.get("source"),
            }
        elif nid.startswith("infra:"):
            infrastructure[nid] = {
                "id": nid, "name": node.get("name", nid.split(":")[-1]),
                "type": node.get("type"), "image": node.get("image"), "serves": [],
            }
        elif nid.startswith("ext:"):
            external_services[nid] = {
                "id": nid, "name": node.get("name", nid.split(":")[-1]),
                "type": "external_service", "consumed_by": [],
            }

    # Enrich from code_structure
    for module in code_structure.get("modules", []):
        mod_path = module["path"]
        mod_name = mod_path.split("/")[-1] if "/" in mod_path else mod_path
        comp = None
        for c in components.values():
            if c.get("path") == mod_path or c["name"] == mod_name:
                comp = c
                break
        if not comp:
            continue

        key_classes = []
        key_functions = []
        for file_info in module.get("files", []):
            for cls in file_info.get("classes", []):
                if isinstance(cls, dict):
                    entry = {"name": cls.get("name", "")}
                    if cls.get("bases"):
                        entry["bases"] = cls["bases"]
                    if cls.get("methods"):
                        if isinstance(cls["methods"][0], dict):
                            entry["methods"] = [m["name"] for m in cls["methods"]]
                        else:
                            entry["methods"] = cls["methods"]
                    if cls.get("collaborators"):
                        entry["collaborators"] = cls["collaborators"]
                    key_classes.append(entry)
            for func in file_info.get("decorated_functions", []):
                if isinstance(func, dict):
                    key_functions.append({"name": func.get("name", ""), "decorators": func.get("decorators", [])})
            for route in file_info.get("route_registrations", []):
                key_functions.append({"name": f"{route['method']} {route['path']}", "type": "route"})

        if key_classes:
            comp["key_classes"] = key_classes[:10]
        if key_functions:
            comp["key_functions"] = key_functions[:15]
        comp["language"] = module.get("language") or comp.get("language")

    # Enrich from manifests
    for api_def in manifests.get("api_definitions", []):
        source = api_def.get("source_file", "")
        for comp in components.values():
            if comp.get("path") and comp["path"] in source:
                comp["api_endpoints"] = api_def.get("endpoints", [])[:15]
                break

    db_schemas = manifests.get("database_schemas", [])
    if db_schemas:
        all_tables = []
        for schema in db_schemas:
            all_tables.extend(schema.get("tables", []))
        for edge in dep_graph.get("edges", []):
            if edge["type"] == "data_access" and edge["from"] in components:
                comp = components[edge["from"]]
                if "data_models" not in comp:
                    comp["data_models"] = all_tables[:10]

    # Build dependency edges (deprecated — kept for backward compat)
    for edge in dep_graph.get("edges", []):
        src, tgt = edge["from"], edge["to"]
        if src in components:
            components[src].setdefault("dependencies_out", []).append(
                {"target": tgt, "type": edge["type"], "evidence": edge.get("evidence", "")}
            )
        if tgt in infrastructure and src not in infrastructure[tgt]["serves"]:
            infrastructure[tgt]["serves"].append(src)
        if tgt in external_services and src not in external_services[tgt]["consumed_by"]:
            external_services[tgt]["consumed_by"].append(src)

    # Infer component roles
    for comp in components.values():
        comp["role"] = _infer_component_role(comp)

    # Deployment context
    deployment = {}
    topo = manifests.get("deployment_topology")
    if topo:
        deployment["containerized"] = True
        deployment["orchestration"] = "docker-compose"
        deployment["service_count"] = len(topo.get("services", []))
    if profile.get("tech_stack", {}).get("iac"):
        deployment["iac_tool"] = profile["tech_stack"]["iac"][0]
    if profile.get("tech_stack", {}).get("ci_cd"):
        deployment["ci_cd"] = profile["tech_stack"]["ci_cd"]

    # Entry points from Dockerfiles and profile
    entry_points = []
    for df in manifests.get("dockerfiles", []):
        if df.get("cmd"):
            entry_points.append({"source": df.get("source_file", ""), "cmd": df["cmd"]})
    for f in profile.get("architecturally_relevant_files", []):
        if f.get("category") == "entry_point":
            entry_points.append({"source": f["path"], "type": "file"})
    if entry_points:
        deployment["entry_points"] = entry_points

    # Config surface for infrastructure
    infra_list = list(infrastructure.values())
    config_map = _build_config_surface(infra_list, manifests)
    for node in infra_list:
        if node["id"] in config_map:
            node["config_surface"] = config_map[node["id"]]

    # Diff awareness
    comp_list = list(components.values())
    changed_ids = set()
    diff_block = None
    if diff_stats:
        diff_block, changed_ids = _build_diff(diff_stats, comp_list, base_branch)
    for comp in comp_list:
        comp["changed"] = comp["id"] in changed_ids

    # Assemble result
    result = {
        "type": "architecture_notes",
        "version": TEMPLATE_VERSION,
        "provenance": _build_provenance(clone_result),
        "meta": _build_meta(profile, clone_result, base_branch),
        "summary": summary,
        "components": comp_list,
        # Directed: from=caller/dependent → to=target/dependency
        "edges": _build_edges(dep_graph),
        "infrastructure": infra_list,
        "external_services": list(external_services.values()),
    }
    if deployment:
        result["deployment"] = deployment
    if diff_block:
        result["diff"] = diff_block
    readme = manifests.get("readme_excerpt")
    if readme:
        result["readme_excerpt"] = readme

    result["_deprecated"] = [
        "summary.repo_name (moved to meta)",
        "components[].dependencies_out (use top-level edges)",
        "components[].key_functions",
        "components[].api_endpoints",
        "components[].data_models",
        "external_services",
        "readme_excerpt",
    ]

    return result
