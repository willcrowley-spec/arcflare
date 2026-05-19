from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


CODE_LABEL_LIMITS: dict[str, int] = {
    "Route": 160,
    "Class": 220,
    "Interface": 120,
    "Function": 260,
    "Method": 260,
    "File": 260,
    "Module": 120,
}

CODE_EDGE_TYPES = ("HANDLES", "CALLS", "HTTP_CALLS", "IMPORTS", "TESTS", "DEFINES")


@dataclass
class CodeGraphNode:
    external_id: str
    label: str
    kind: str
    qualified_name: str | None = None
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    in_degree: int = 0
    out_degree: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeGraphEdge:
    source_external_id: str
    target_external_id: str
    edge_type: str
    confidence: float = 0.75
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeGraphProject:
    project_id: str
    label: str
    root_path: str
    indexed_at: str | None = None
    nodes: list[CodeGraphNode] = field(default_factory=list)
    edges: list[CodeGraphEdge] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    status: str = "indexed"
    provider: str = "codebase-memory-mcp"


def parse_codegraph_repos(value: str | None) -> list[tuple[str, str]]:
    """Parse `name=/path; /unnamed/path` into stable repo aliases and paths."""
    if not value:
        return []
    stripped = value.strip()
    if not stripped:
        return []

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = []
        repos: list[tuple[str, str]] = []
        for item in parsed if isinstance(parsed, list) else []:
            if isinstance(item, str):
                path = item.strip()
                repos.append((_alias_from_path(path), path))
            elif isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                alias = str(item.get("name") or item.get("alias") or _alias_from_path(path)).strip()
                if path:
                    repos.append((_slug(alias), path))
        return repos

    repos = []
    for raw_part in stripped.replace("\n", ";").split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" in part:
            alias, path = part.split("=", 1)
            alias = _slug(alias.strip())
            path = path.strip()
        else:
            path = part
            alias = _alias_from_path(path)
        if path:
            repos.append((alias, path))
    return repos


def code_node_type(kind: str) -> str:
    normalized = kind.strip().lower().replace(" ", "_")
    return {
        "project": "code_project",
        "file": "code_file",
        "folder": "code_folder",
        "module": "code_module",
        "package": "code_module",
        "route": "code_route",
        "function": "code_function",
        "method": "code_function",
        "class": "code_class",
        "interface": "code_class",
        "type": "code_type",
        "variable": "code_symbol",
        "section": "code_section",
    }.get(normalized, "code_symbol")


def code_edge_type(edge_type: str) -> str:
    normalized = edge_type.strip().lower()
    return {
        "defines": "defines",
        "defines_method": "defines",
        "contains_file": "contains",
        "contains_folder": "contains",
        "calls": "calls",
        "http_calls": "http_calls",
        "async_calls": "async_calls",
        "imports": "imports",
        "handles": "handles",
        "tests": "tests",
        "implements": "implements",
        "inherits": "inherits",
        "usage": "uses",
        "writes": "writes",
        "decorates": "decorates",
        "defined_in": "defined_in",
    }.get(normalized, normalized or "depends_on")


class CodeGraphProvider:
    def load_projects(self) -> list[CodeGraphProject]:
        raise NotImplementedError


class NullCodeGraphProvider(CodeGraphProvider):
    def load_projects(self) -> list[CodeGraphProject]:
        return []


class CodebaseMemoryProjectReader:
    def __init__(self, *, project_alias: str, root_path: str) -> None:
        self.project_alias = _slug(project_alias)
        self.root_path = root_path

    def from_cli_payloads(
        self,
        *,
        index_payload: dict[str, Any],
        architecture_payload: dict[str, Any],
        search_payloads: dict[str, dict[str, Any]],
        edge_payloads: dict[str, dict[str, Any]],
    ) -> CodeGraphProject:
        project_id = _slug(str(index_payload.get("project") or self.project_alias))
        nodes_by_external_id: dict[str, CodeGraphNode] = {}
        external_by_qualified_name: dict[str, str] = {}

        def add_node(node: CodeGraphNode) -> None:
            existing = nodes_by_external_id.get(node.external_id)
            if existing:
                existing.in_degree = max(existing.in_degree, node.in_degree)
                existing.out_degree = max(existing.out_degree, node.out_degree)
                existing.metadata.update(node.metadata)
                return
            nodes_by_external_id[node.external_id] = node
            if node.qualified_name:
                external_by_qualified_name[node.qualified_name] = node.external_id

            if node.file_path and node.kind.lower() != "file":
                file_node = _file_node(node.file_path)
                if file_node.external_id not in nodes_by_external_id:
                    nodes_by_external_id[file_node.external_id] = file_node

        for label, payload in search_payloads.items():
            for item in payload.get("results") or []:
                if not isinstance(item, dict):
                    continue
                add_node(_node_from_search_result(item, fallback_kind=label))

        for route in architecture_payload.get("routes") or []:
            if not isinstance(route, dict):
                continue
            method = str(route.get("method") or "ANY").upper()
            path = str(route.get("path") or "").strip()
            handler = str(route.get("handler") or "").strip()
            if not path:
                continue
            qualified_name = f"__route__{method}__{path}"
            add_node(
                CodeGraphNode(
                    external_id=_external_id("Route", qualified_name),
                    label=f"{method} {path}",
                    kind="Route",
                    qualified_name=qualified_name,
                    metadata={"handler": handler},
                )
            )

        for hotspot in architecture_payload.get("hotspots") or []:
            if not isinstance(hotspot, dict):
                continue
            qualified_name = str(hotspot.get("qualified_name") or "").strip()
            name = str(hotspot.get("name") or qualified_name).strip()
            if not qualified_name and not name:
                continue
            add_node(
                CodeGraphNode(
                    external_id=_external_id("Hotspot", qualified_name or name),
                    label=name or qualified_name,
                    kind="Function",
                    qualified_name=qualified_name or None,
                    in_degree=_int(hotspot.get("fan_in")),
                    metadata={"source": "architecture_hotspot"},
                )
            )

        edges: list[CodeGraphEdge] = []
        for edge_type, payload in edge_payloads.items():
            for row in payload.get("rows") or []:
                edge = self._edge_from_row(row, edge_type, nodes_by_external_id, external_by_qualified_name)
                if edge:
                    edges.append(edge)

        for node in list(nodes_by_external_id.values()):
            if node.file_path and node.kind.lower() != "file":
                file_node = _file_node(node.file_path)
                nodes_by_external_id.setdefault(file_node.external_id, file_node)
                edges.append(
                    CodeGraphEdge(
                        source_external_id=node.external_id,
                        target_external_id=file_node.external_id,
                        edge_type="DEFINED_IN",
                        confidence=0.8,
                    )
                )

        metrics = {
            "total_nodes": _int(index_payload.get("nodes") or architecture_payload.get("total_nodes")),
            "total_edges": _int(index_payload.get("edges") or architecture_payload.get("total_edges")),
            "node_labels": architecture_payload.get("node_labels") or [],
            "edge_types": architecture_payload.get("edge_types") or [],
            "languages": architecture_payload.get("languages") or [],
            "routes": len(architecture_payload.get("routes") or []),
            "hotspots": len(architecture_payload.get("hotspots") or []),
            "rendered_nodes": len(nodes_by_external_id),
            "rendered_edges": len(edges),
        }

        return CodeGraphProject(
            project_id=project_id,
            label=self.project_alias.replace("-", " ").title() or project_id,
            root_path=self.root_path,
            nodes=sorted(nodes_by_external_id.values(), key=lambda node: node.external_id),
            edges=_dedupe_edges(edges),
            metrics=metrics,
            status=str(index_payload.get("status") or "indexed"),
        )

    def _edge_from_row(
        self,
        row: object,
        fallback_edge_type: str,
        nodes_by_external_id: dict[str, CodeGraphNode],
        external_by_qualified_name: dict[str, str],
    ) -> CodeGraphEdge | None:
        if not isinstance(row, list) or len(row) < 9:
            return None
        source_name, source_qn, source_kind, source_file, edge_type, target_name, target_qn, target_kind, target_file = [
            "" if value is None else str(value) for value in row[:9]
        ]
        source = _node_from_parts(source_name, source_qn, source_kind, source_file)
        target = _node_from_parts(target_name, target_qn, target_kind, target_file)
        for node in (source, target):
            if node.external_id not in nodes_by_external_id:
                nodes_by_external_id[node.external_id] = node
            if node.qualified_name:
                external_by_qualified_name.setdefault(node.qualified_name, node.external_id)
        return CodeGraphEdge(
            source_external_id=external_by_qualified_name.get(source_qn) or source.external_id,
            target_external_id=external_by_qualified_name.get(target_qn) or target.external_id,
            edge_type=edge_type or fallback_edge_type,
            confidence=0.82,
        )


class CodebaseMemoryProvider(CodeGraphProvider):
    def __init__(
        self,
        *,
        binary_path: str,
        repos: list[tuple[str, str]],
        mode: str = "fast",
        timeout_seconds: int = 45,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.binary_path = binary_path
        self.repos = repos
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: tuple[float, list[CodeGraphProject]] | None = None

    def load_projects(self) -> list[CodeGraphProject]:
        if not self.repos:
            return []
        if not self._binary_available():
            logger.warning("codebase_memory_binary_missing path=%s", self.binary_path)
            return []

        now = monotonic()
        if self._cache and now - self._cache[0] < self.cache_ttl_seconds:
            return self._cache[1]

        projects: list[CodeGraphProject] = []
        for alias, root_path in self.repos:
            try:
                projects.append(self._load_project(alias, root_path))
            except Exception:
                logger.warning(
                    "codebase_memory_project_load_failed alias=%s root=%s",
                    alias,
                    root_path,
                    exc_info=True,
                )
        self._cache = (now, projects)
        return projects

    def _load_project(self, alias: str, root_path: str) -> CodeGraphProject:
        reader = CodebaseMemoryProjectReader(project_alias=alias, root_path=root_path)
        index_payload = self._run_tool(
            "index_repository",
            {"repo_path": root_path, "mode": self.mode, "persistence": False},
        )
        project_name = str(index_payload.get("project") or alias)
        architecture_payload = self._run_tool(
            "get_architecture",
            {"project": project_name, "aspects": ["all"]},
        )
        search_payloads = {
            label: self._run_tool(
                "search_graph",
                {"project": project_name, "label": label, "limit": limit},
            )
            for label, limit in CODE_LABEL_LIMITS.items()
        }
        edge_payloads = {
            edge_type: self._run_tool(
                "query_graph",
                {
                    "project": project_name,
                    "query": (
                        f"MATCH (a)-[r:{edge_type}]->(b) "
                        "RETURN a.name, a.qualified_name, a.label, a.file_path, "
                        "r.type, b.name, b.qualified_name, b.label, b.file_path "
                        "LIMIT 450"
                    ),
                },
            )
            for edge_type in CODE_EDGE_TYPES
        }
        return reader.from_cli_payloads(
            index_payload=index_payload,
            architecture_payload=architecture_payload,
            search_payloads=search_payloads,
            edge_payloads=edge_payloads,
        )

    def _run_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = subprocess.run(
            [self.binary_path, "cli", tool_name, json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"codebase-memory-mcp {tool_name} failed with {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()[:800]}"
            )
        stdout = result.stdout.strip()
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"codebase-memory-mcp {tool_name} returned non-JSON output") from exc

    def _binary_available(self) -> bool:
        return Path(self.binary_path).exists() or shutil.which(self.binary_path) is not None


_configured_provider: CodeGraphProvider | None = None


def get_configured_code_graph_provider() -> CodeGraphProvider:
    global _configured_provider
    if _configured_provider is not None:
        return _configured_provider

    settings = get_settings()
    if not settings.ARCBRAIN_CODEGRAPH_ENABLED:
        _configured_provider = NullCodeGraphProvider()
        return _configured_provider

    repos = parse_codegraph_repos(settings.ARCBRAIN_CODEGRAPH_REPOS)
    if settings.ARCBRAIN_CODEGRAPH_PROVIDER != "codebase_memory" or not repos:
        _configured_provider = NullCodeGraphProvider()
        return _configured_provider

    _configured_provider = CodebaseMemoryProvider(
        binary_path=settings.ARCBRAIN_CODEGRAPH_BINARY,
        repos=repos,
        mode=settings.ARCBRAIN_CODEGRAPH_MODE,
        timeout_seconds=settings.ARCBRAIN_CODEGRAPH_TIMEOUT_SECONDS,
        cache_ttl_seconds=settings.ARCBRAIN_CODEGRAPH_CACHE_TTL_SECONDS,
    )
    return _configured_provider


def _node_from_search_result(item: dict[str, Any], *, fallback_kind: str) -> CodeGraphNode:
    kind = str(item.get("label") or fallback_kind or "Symbol")
    qualified_name = _str_or_none(item.get("qualified_name"))
    label = str(item.get("name") or qualified_name or item.get("file_path") or kind)
    file_path = _str_or_none(item.get("file_path"))
    return CodeGraphNode(
        external_id=_external_id(kind, qualified_name or file_path or label),
        label=label,
        kind=kind,
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=_optional_int(item.get("start_line")),
        end_line=_optional_int(item.get("end_line")),
        in_degree=_int(item.get("in_degree")),
        out_degree=_int(item.get("out_degree")),
        metadata={k: v for k, v in item.items() if k not in {"name", "label", "qualified_name", "file_path"}},
    )


def _node_from_parts(name: str, qualified_name: str, kind: str, file_path: str) -> CodeGraphNode:
    kind = kind or "Symbol"
    label = name or qualified_name or file_path or kind
    return CodeGraphNode(
        external_id=_external_id(kind, qualified_name or file_path or label),
        label=label,
        kind=kind,
        qualified_name=qualified_name or None,
        file_path=file_path or None,
    )


def _file_node(file_path: str) -> CodeGraphNode:
    return CodeGraphNode(
        external_id=_external_id("File", file_path),
        label=file_path,
        kind="File",
        qualified_name=None,
        file_path=file_path,
    )


def _dedupe_edges(edges: list[CodeGraphEdge]) -> list[CodeGraphEdge]:
    deduped: dict[tuple[str, str, str], CodeGraphEdge] = {}
    for edge in edges:
        key = (edge.source_external_id, edge.target_external_id, edge.edge_type)
        deduped.setdefault(key, edge)
    return sorted(deduped.values(), key=lambda edge: (edge.edge_type, edge.source_external_id, edge.target_external_id))


def _external_id(kind: str, value: str) -> str:
    return f"{code_node_type(kind)}:{value}".strip()


def _alias_from_path(path: str) -> str:
    name = Path(path.replace("\\", "/")).name or "codebase"
    return _slug(name)


def _slug(value: str) -> str:
    cleaned = value.strip().lower().replace("\\", "/").replace("_", "-")
    return "-".join(part for part in cleaned.replace("/", " ").split() if part) or "codebase"


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return _int(value)


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
