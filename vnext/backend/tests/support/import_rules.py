"""Backend import-boundary rules used by ``tests/test_architecture.py``.

The rules encode the P5 §2A.2 guardrails as precise module/symbol checks. Existing violations are
frozen in ``tests/architecture_baseline.py``; ``test_architecture.py`` fails on any new violation
and on any baseline entry that no longer occurs, so the baseline can only shrink.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"
BACKEND_PACKAGE = "gateway_backend"
PRODUCTION_ENTRYPOINTS = (
    "gateway_backend.app",
    "gateway_backend.bootstrap.http_server",
    "gateway_backend.bootstrap.operation_worker",
    "gateway_backend.bootstrap.storage_admin",
)
# Package-root modules that belong to process composition rather than to an unowned bucket.
COMPOSITION_MODULES = frozenset(
    {
        "gateway_backend",
        "gateway_backend.app",
        "gateway_backend.settings",
        "gateway_backend.deployment_config",
        "gateway_backend.runtime_preflight",
    }
)

# Exact shared owners: identity is a domain value; host documents are composition; document_fields
# is a pure field-reader leaf shared by application and capability codecs.
OWNED_ROOT_MODULES = {
    "gateway_backend.device_identity": "domain",
    "gateway_backend.document_fields": "document_fields",
    "gateway_backend.processing_group_config": "composition",
}

RULE_LAYER = "layer"
RULE_HTTP_POLICY = "http-policy"
RULE_CAPABILITY_SURFACE = "capability-surface"
RULE_PRIVATE = "private"
RULE_UNOWNED_ROOT = "unowned-root-module"
RULE_CONTRACTS_LEAF = "contracts-leaf"

# Target categories used in the allow-lists below.
ANY_CAPABILITY = "capability:*"
ANY_INFRASTRUCTURE = "infrastructure:*"
APPLICATION_PORTS = "application:ports"
_APPLICATION_PORT_MODULE_NAMES = frozenset({"ports", "contracts", "errors"})

_EXTERNAL_ZONES = (
    ("gateway_shared_kernel.testing", "ext:shared_kernel_testing"),
    ("gateway_shared_kernel", "shared_kernel"),
    ("gateway_repository_service", "ext:repository_service"),
    ("gateway_repository_client", "ext:repository_client"),
    ("gateway_repository_contracts", "ext:repository_wire"),
    ("gateway_compute", "ext:compute"),
    ("backend_vnext", "ext:legacy"),
    ("legacy", "ext:legacy"),
    ("sqlite3", "ext:sqlite"),
    ("fastapi", "ext:web"),
    ("starlette", "ext:web"),
    ("uvicorn", "ext:web"),
    ("httpx", "ext:http_client"),
    ("sqlalchemy", "ext:orm"),
    ("alembic", "ext:orm"),
)
_FORBIDDEN_EVERYWHERE = frozenset(
    {"ext:repository_service", "ext:shared_kernel_testing", "ext:legacy", "ext:orm"}
)

_REPOSITORY_ADAPTER_EDGES = frozenset(
    {
        ANY_INFRASTRUCTURE,
        "domain",
        "operations",
        "artifacts",
        APPLICATION_PORTS,
        ANY_CAPABILITY,
        "ext:repository_client",
        "ext:repository_wire",
        "ext:http_client",
    }
)

# Allowed target zones per source zone. ``shared_kernel`` and unconstrained third-party/stdlib
# modules are always allowed. Capability-to-capability edges are further restricted by the
# capability DAG test; composition roots may wire anything except the always-forbidden zones.
ALLOWED_ZONE_EDGES: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "artifacts": frozenset({"artifacts"}),
    "operations": frozenset({"operations", "artifacts"}),
    "statistics": frozenset({"statistics", "operations", "ext:repository_wire"}),
    "infrastructure:statistics": frozenset(
        {"statistics", "operations", "ext:repository_wire", "ext:sqlite"}
    ),
    "capabilities": frozenset(),
    "capability": frozenset({ANY_CAPABILITY, "artifacts", "document_fields"}),
    "cache": frozenset({"cache", "artifacts", ANY_CAPABILITY}),
    "document_fields": frozenset(),
    "application": frozenset(
        {"application", "domain", "operations", "artifacts", "document_fields", ANY_CAPABILITY}
    ),
    "http": frozenset({"http", "application", "domain", "operations", "artifacts", "ext:web"}),
    "infrastructure:control_db": frozenset(
        {ANY_INFRASTRUCTURE, "domain", "operations", "artifacts", APPLICATION_PORTS, "ext:sqlite"}
    ),
    "infrastructure:artifact_store": frozenset({ANY_INFRASTRUCTURE, "domain", "artifacts"}),
    "infrastructure:repository_read": _REPOSITORY_ADAPTER_EDGES,
    "infrastructure:repository_write": _REPOSITORY_ADAPTER_EDGES,
}
COMPOSITION_ZONES = frozenset({"composition", "bootstrap"})

# Rust policy §4: exact coarse entrypoints, not a capability-wide compute
# exemption. Other owners, whole-module imports and wildcard imports still fail.
NATIVE_COMPUTE_ENTRYPOINTS: dict[str, frozenset[str]] = {
    "gateway_backend.bootstrap.compute_kernel": frozenset({"_init_kernel_native"}),
    "gateway_backend.capabilities.comparison.native": frozenset(
        {
            "_begin_comparison_operation_native",
            "_standard_identity_scanner_native",
            "_compare_records_native",
            "_facts_core_digest_native",
            "_summarize_unchanged_ordered_native",
            "_validate_records_batches_native",
            "_restore_comparison_table_native",
            "_comparison_format_versions_native",
        }
    ),
    "gateway_backend.capabilities.mutation_planning.native": frozenset(
        {
            "_begin_storage_operation_native",
            "_prepare_storage_table_native",
            "_render_change_set_native",
        }
    ),
    "gateway_backend.capabilities.table_access.native": frozenset({"_parse_sql_native"}),
    "gateway_backend.capabilities.snapshot_materialization.native": frozenset(
        {"_sql_materialize_native", "_catalog_filter_native"}
    ),
    "gateway_backend.capabilities.storage_projection.native": frozenset(
        {
            "_canonical_project_native",
            "_render_storage_schema_native",
        }
    ),
    "gateway_backend.capabilities.snapshot_materialization.canonical_store": frozenset(
        {
            "_canonical_comparison_profile_native",
            "_encode_canonical_ipc_native",
            "_inspect_canonical_ipc_native",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source: str
    target: str
    names: tuple[str, ...]
    context: str  # "module" | "function" | "type_checking"
    path: Path
    line: int
    function: str | None = None


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    source: str
    target: str
    path: Path
    line: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.rule, self.source, self.target)

    def describe(self) -> str:
        try:
            display_path = self.path.relative_to(BACKEND_SRC.parent)
        except ValueError:
            display_path = self.path
        location = f"{display_path}:{self.line}"
        return f"[{self.rule}] {self.source} -> {self.target}  ({location})"


def module_name(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(BACKEND_SRC).with_suffix("").parts)
    is_init = parts[-1] == "__init__"
    if is_init:
        parts = parts[:-1]
    return ".".join(parts), is_init


def backend_sources() -> list[Path]:
    return sorted(
        path
        for path in (BACKEND_SRC / BACKEND_PACKAGE).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def backend_modules() -> dict[str, Path]:
    return {module_name(path)[0]: path for path in backend_sources()}


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self, source: str, is_init: bool, path: Path, modules: dict[str, Path]) -> None:
        self._source = source
        self._is_init = is_init
        self._path = path
        self._modules = modules
        self._function_depth = 0
        self._function_scope: str | None = None
        self._type_checking_depth = 0
        self.edges: list[ImportEdge] = []
        self.reexports: dict[str, tuple[str, str | None]] = {}

    def _context(self) -> str:
        if self._type_checking_depth:
            return "type_checking"
        if self._function_depth:
            return "function"
        return "module"

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_type_checking:
            self.generic_visit(node)
            return
        self._type_checking_depth += 1
        for child in node.body:
            self.visit(child)
        self._type_checking_depth -= 1
        for child in node.orelse:
            self.visit(child)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous_scope = self._function_scope
        if self._function_depth == 0:
            self._function_scope = node.name
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1
        self._function_scope = previous_scope

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        previous_scope = self._function_scope
        if self._function_depth == 0:
            self._function_scope = node.name
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1
        self._function_scope = previous_scope

    def visit_Import(self, node: ast.Import) -> None:
        in_reexport_scope = self._context() in {"module", "type_checking"}
        for alias in node.names:
            self._add(alias.name, (), node.lineno)
            if in_reexport_scope:
                if alias.asname is not None:
                    self.reexports[alias.asname] = (alias.name, None)
                else:
                    top_name = alias.name.split(".", 1)[0]
                    self.reexports[top_name] = (top_name, None)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        aliases = tuple((alias.name, alias.asname) for alias in node.names)
        if node.level == 0:
            assert node.module is not None
            self._add_from(node.module, aliases, node.lineno)
            return
        parts = self._source.split(".")
        if not self._is_init:
            parts = parts[:-1]
        if node.level > 1:
            parts = parts[: -(node.level - 1)]
        base = ".".join([*parts, *node.module.split(".")]) if node.module else ".".join(parts)
        self._add_from(base, aliases, node.lineno)

    def _add_from(
        self,
        base: str,
        aliases: tuple[tuple[str, str | None], ...],
        line: int,
    ) -> None:
        # ``from pkg import submodule`` targets the submodule; remaining names target ``pkg``.
        in_reexport_scope = self._context() in {"module", "type_checking"}
        attribute_names: list[str] = []
        for name, asname in aliases:
            candidate = f"{base}.{name}"
            if candidate in self._modules:
                self._add(candidate, (), line)
                if in_reexport_scope:
                    self.reexports[asname or name] = (candidate, None)
            else:
                attribute_names.append(name)
                if in_reexport_scope and name != "*":
                    self.reexports[asname or name] = (base, name)
        if attribute_names or not aliases:
            self._add(base, tuple(attribute_names), line)

    def _add(self, target: str, names: tuple[str, ...], line: int) -> None:
        if target == "__future__":
            return
        self.edges.append(
            ImportEdge(
                self._source,
                target,
                names,
                self._context(),
                self._path,
                line,
                self._function_scope if self._function_depth else None,
            )
        )


def _collect_edges_and_reexports(
    modules: dict[str, Path] | None = None,
) -> tuple[list[ImportEdge], dict[str, dict[str, tuple[str, str | None]]]]:
    known = modules if modules is not None else backend_modules()
    edges: list[ImportEdge] = []
    reexports: dict[str, dict[str, tuple[str, str | None]]] = {}
    for source, path in sorted(known.items(), key=lambda item: item[1]):
        is_init = path.name == "__init__.py"
        visitor = _ImportVisitor(source, is_init, path, known)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        edges.extend(visitor.edges)
        if visitor.reexports:
            reexports[source] = visitor.reexports
    return edges, reexports


def collect_edges(modules: dict[str, Path] | None = None) -> list[ImportEdge]:
    edges, _reexports = _collect_edges_and_reexports(modules)
    return edges


def collect_reexports(
    modules: dict[str, Path] | None = None,
) -> dict[str, dict[str, tuple[str, str | None]]]:
    _edges, reexports = _collect_edges_and_reexports(modules)
    return reexports


def package_names(modules: dict[str, Path]) -> frozenset[str]:
    return frozenset(name for name, path in modules.items() if path.name == "__init__.py")


def zone(module: str, packages: frozenset[str]) -> str | None:
    """Return the architectural zone of ``module``; ``None`` means unconstrained."""

    parts = module.split(".")
    if parts[0] != BACKEND_PACKAGE:
        for prefix, external in _EXTERNAL_ZONES:
            if module == prefix or module.startswith(f"{prefix}."):
                return external
        return None
    if module in OWNED_ROOT_MODULES:
        return OWNED_ROOT_MODULES[module]
    if module in COMPOSITION_MODULES:
        return "composition"
    top = f"{BACKEND_PACKAGE}.{parts[1]}"
    if top not in packages:
        return "root"
    if parts[1] == "capabilities":
        return "capabilities" if len(parts) == 2 else f"capability:{parts[2]}"
    if parts[1] == "infrastructure":
        return "infrastructure" if len(parts) == 2 else f"infrastructure:{parts[2]}"
    return parts[1]


def _target_category_allowed(allowed: frozenset[str], target_zone: str, target: str) -> bool:
    if target_zone in allowed:
        return True
    if target_zone.startswith("capability:") and ANY_CAPABILITY in allowed:
        return True
    if target_zone.startswith("infrastructure:") and ANY_INFRASTRUCTURE in allowed:
        return True
    if (
        target_zone == "application"
        and APPLICATION_PORTS in allowed
        and target.rsplit(".", 1)[-1] in _APPLICATION_PORT_MODULE_NAMES
    ):
        return True
    return False


def _private_owner(module: str) -> str | None:
    """Return the package that owns the first private segment of ``module``, if any."""

    parts = module.split(".")
    for index, part in enumerate(parts[1:], start=1):
        if part.startswith("_") and not part.startswith("__"):
            return ".".join(parts[:index])
    return None


def _is_private_name(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def _within(source: str, package: str) -> bool:
    return source == package or source.startswith(f"{package}.")


def _package_dir(module: str, packages: frozenset[str]) -> str:
    if module in packages:
        return module
    return module.rsplit(".", 1)[0] if "." in module else module


def _resolve_symbol_origin(
    target: str,
    name: str,
    modules: Mapping[str, Path],
    reexports: Mapping[str, Mapping[str, tuple[str, str | None]]],
) -> tuple[str, str | None]:
    current_module = target
    current_name: str | None = name
    seen: set[tuple[str, str | None]] = set()
    while (current_module, current_name) not in seen:
        seen.add((current_module, current_name))
        if current_name is None:
            break
        submodule = f"{current_module}.{current_name}"
        if submodule in modules:
            current_module = submodule
            current_name = None
            continue
        binding = reexports.get(current_module, {}).get(current_name)
        if binding is None:
            break
        current_module, current_name = binding
    return current_module, current_name


def _is_domain_policies_target(target: str, names: tuple[str, ...]) -> bool:
    parts = target.split(".")
    if len(parts) >= 4 and parts[0] == BACKEND_PACKAGE and parts[1] == "domain":
        return parts[3] == "policies"
    if len(parts) == 3 and parts[0] == BACKEND_PACKAGE and parts[1] == "domain":
        return "policies" in names
    return False


def classify_edge(
    edge: ImportEdge,
    packages: frozenset[str],
    *,
    modules: Mapping[str, Path] | None = None,
    reexports: Mapping[str, Mapping[str, tuple[str, str | None]]] | None = None,
) -> tuple[str, str] | None:
    """Return the first rule an edge breaks, as ``(rule, target)``.

    Precedence: an edge that must not exist at all (layer) is reported once; otherwise private
    access, then non-public capability modules, then contracts importing their own execution code.
    """

    source_zone = zone(edge.source, packages)
    target_zone = zone(edge.target, packages)
    if source_zone is None or source_zone == "root":
        # Unowned root modules are reported once by RULE_UNOWNED_ROOT.
        return None

    if target_zone == "ext:compute" and not (
        edge.target == "gateway_compute._native"
        and bool(edge.names)
        and set(edge.names) <= NATIVE_COMPUTE_ENTRYPOINTS.get(edge.source, frozenset())
    ):
        return (RULE_LAYER, edge.target)

    if target_zone in _FORBIDDEN_EVERYWHERE:
        return (RULE_LAYER, edge.target)
    if (
        target_zone is not None
        and target_zone != "shared_kernel"
        and target_zone != source_zone
        and source_zone not in COMPOSITION_ZONES
    ):
        allowed_key = (
            source_zone
            if source_zone in ALLOWED_ZONE_EDGES
            else ("capability" if source_zone.startswith("capability:") else source_zone)
        )
        allowed = ALLOWED_ZONE_EDGES.get(allowed_key, frozenset())
        approved_native_call = (
            edge.target == "gateway_compute._native"
            and bool(edge.names)
            and set(edge.names) <= NATIVE_COMPUTE_ENTRYPOINTS.get(edge.source, frozenset())
        )
        # Nominal domain refs validate the same closed location protocol through
        # this pure leaf function. Artifact models, constructors and IO stay out.
        approved_artifact_id_codec = (
            source_zone == "domain"
            and edge.target == "gateway_backend.artifacts.location"
            and edge.names == ("parse_artifact_id",)
        )
        approved_telemetry_hook = edge.target == "gateway_backend.statistics.metrics"
        approved_telemetry_port = (
            source_zone == "operations" and edge.target == "gateway_backend.statistics.ports"
        )
        approved_statistics_model = source_zone in {"http", "application"} and edge.target in {
            "gateway_backend.statistics.models",
            "gateway_backend.statistics.queries",
        }
        approved_statistics_wire = (
            edge.source == "gateway_backend.http.schemas.statistics"
            and edge.target == "gateway_repository_contracts.statistics"
        )
        # The storage telemetry adapter reads only the owning fixed ref decoders and
        # live stat; it cannot call application/capabilities or mutate business state.
        approved_statistics_storage = (
            edge.source == "gateway_backend.infrastructure.statistics.storage"
            and edge.target
            in {
                "gateway_backend.artifacts.computation_cache",
                "gateway_backend.artifacts.location",
                "gateway_backend.artifacts.serialize",
                "gateway_backend.artifacts.store",
                "gateway_backend.infrastructure.artifact_store.local_store",
                "gateway_backend.infrastructure.control_db.computation_cache",
                "gateway_backend.infrastructure.control_db.sqlite_workspace",
                "gateway_backend.infrastructure.control_db.sqlite_submission",
            }
        )
        if (
            not _target_category_allowed(allowed, target_zone, edge.target)
            and not approved_native_call
            and not approved_artifact_id_codec
            and not approved_telemetry_hook
            and not approved_telemetry_port
            and not approved_statistics_model
            and not approved_statistics_wire
            and not approved_statistics_storage
        ):
            return (RULE_LAYER, edge.target)

    if source_zone == "http" and _is_domain_policies_target(edge.target, edge.names):
        return (RULE_HTTP_POLICY, edge.target)

    if _within(edge.target, BACKEND_PACKAGE):
        source_dir = _package_dir(edge.source, packages)
        target_dir = _package_dir(edge.target, packages)
        private_owner = _private_owner(edge.target)
        if private_owner is not None and source_dir != target_dir:
            return (RULE_PRIVATE, edge.target)
        violating_names: list[str] = []
        for name in edge.names:
            origin_module, origin_name = _resolve_symbol_origin(
                edge.target,
                name,
                modules or {},
                reexports or {},
            )
            origin_in_backend = _within(origin_module, BACKEND_PACKAGE)
            origin_dir = _package_dir(origin_module, packages)
            if _is_private_name(name):
                if source_dir != target_dir or (origin_in_backend and source_dir != origin_dir):
                    violating_names.append(
                        name
                        if origin_module == edge.target
                        else f"{name} (defined in {origin_module})"
                    )
            elif (
                origin_in_backend
                and source_dir != origin_dir
                and (
                    (origin_name is None and _private_owner(origin_module) is not None)
                    or (origin_name is not None and _is_private_name(origin_name))
                )
            ):
                label = origin_name if origin_name is not None else origin_module
                violating_names.append(f"{name} -> {origin_module}:{label}")
        if violating_names:
            return (RULE_PRIVATE, f"{edge.target}:{','.join(sorted(set(violating_names)))}")

    if target_zone is not None and target_zone.startswith("capability:"):
        owner_package = ".".join(edge.target.split(".")[:3])
        public_modules = {
            owner_package,
            f"{owner_package}.contracts",
            f"{owner_package}.documents",
        }
        if (
            not _within(edge.source, owner_package)
            and not source_zone.startswith("capability:")
            and edge.target not in public_modules
        ):
            return (RULE_CAPABILITY_SURFACE, edge.target)
        if edge.source == f"{owner_package}.contracts" and edge.target != edge.source:
            return (RULE_CONTRACTS_LEAF, edge.target)
    return None


def find_violations(edges: Iterable[ImportEdge], modules: dict[str, Path]) -> list[Violation]:
    packages = package_names(modules)
    reexports = collect_reexports(modules)
    violations = [
        Violation(RULE_UNOWNED_ROOT, module, "", path, 1)
        for module, path in modules.items()
        if zone(module, packages) == "root"
    ]
    for edge in edges:
        found = classify_edge(edge, packages, modules=modules, reexports=reexports)
        if found is not None:
            rule, target = found
            violations.append(Violation(rule, edge.source, target, edge.path, edge.line))
    return violations


def runtime_cycles(edges: Iterable[ImportEdge], modules: dict[str, Path]) -> list[frozenset[str]]:
    """Strongly connected components (size > 1) of the runtime module import graph."""

    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if (
            edge.context == "type_checking"
            or edge.target not in modules
            or edge.target == edge.source
        ):
            continue
        graph[edge.source].add(edge.target)

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[frozenset[str]] = []
    counter = 0

    def strongconnect(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for successor in sorted(graph.get(node, ())):
            if successor not in index:
                strongconnect(successor)
                low[node] = min(low[node], low[successor])
            elif successor in on_stack:
                low[node] = min(low[node], index[successor])
        if low[node] == index[node]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.add(member)
                if member == node:
                    break
            if len(component) > 1:
                components.append(frozenset(component))

    for node in sorted(modules):
        if node not in index:
            strongconnect(node)
    return sorted(components, key=lambda component: sorted(component))


def unreachable_modules(edges: Iterable[ImportEdge], modules: dict[str, Path]) -> frozenset[str]:
    """Non-package modules that no production entrypoint reaches.

    Facade re-exports resolve to their defining module. Lazy imports inside a facade wrapper count
    only when a reachable module imports that wrapper symbol.
    """

    edge_list = list(edges)
    reexports: dict[str, dict[str, str]] = defaultdict(dict)
    facade_function_imports: dict[tuple[str, str], list[ImportEdge]] = defaultdict(list)
    for edge in edge_list:
        if modules.get(edge.source, Path()).name != "__init__.py":
            continue
        if edge.context == "function" and edge.function is not None:
            facade_function_imports[(edge.source, edge.function)].append(edge)
            continue
        if edge.context != "module" or edge.target not in modules:
            continue
        for name in edge.names:
            reexports[edge.source][name] = edge.target
        if not edge.names and edge.target.startswith(f"{edge.source}."):
            reexports[edge.source][edge.target.rsplit(".", 1)[-1]] = edge.target

    def resolve(package: str, name: str) -> str:
        seen: set[str] = set()
        current = package
        while current in reexports and name in reexports[current] and current not in seen:
            seen.add(current)
            current = reexports[current][name]
        return current

    def _add_edge(source: str, target: str) -> None:
        if target in modules:
            graph[source].add(target)

    def _add_import_dependencies(
        source: str,
        target: str,
        names: tuple[str, ...],
        active_wrappers: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        if target not in modules:
            return
        if not names:
            _add_edge(source, target)
            return
        for name in names:
            wrapper = (target, name)
            wrapper_imports = facade_function_imports.get(wrapper)
            if wrapper_imports is not None:
                if wrapper in active_wrappers:
                    continue
                next_active = active_wrappers | {wrapper}
                for wrapper_edge in wrapper_imports:
                    if wrapper_edge.context == "type_checking":
                        continue
                    _add_import_dependencies(
                        source,
                        wrapper_edge.target,
                        wrapper_edge.names,
                        next_active,
                    )
                continue
            resolved = resolve(target, name) if name in reexports.get(target, {}) else target
            _add_edge(source, resolved)

    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edge_list:
        if edge.context == "type_checking":
            continue
        source_is_init = modules.get(edge.source, Path()).name == "__init__.py"
        if source_is_init:
            continue
        _add_import_dependencies(edge.source, edge.target, edge.names)

    reached = set(PRODUCTION_ENTRYPOINTS)
    pending = list(reached)
    while pending:
        current = pending.pop()
        for target in graph.get(current, ()):
            if target not in reached:
                reached.add(target)
                pending.append(target)
    return frozenset(
        name
        for name, path in modules.items()
        if name not in reached and path.name != "__init__.py" and name != BACKEND_PACKAGE
    )


def iter_baseline_lines() -> Iterator[str]:
    """Render the current state as baseline literals (used to seed/refresh the baseline file)."""

    modules = backend_modules()
    edges = collect_edges(modules)
    keys = sorted({violation.key for violation in find_violations(edges, modules)})
    yield "IMPORT_RULE_BASELINE = frozenset({"
    for key in keys:
        yield f"    {key!r},"
    yield "})"
    yield "RUNTIME_CYCLE_BASELINE = ("
    for component in runtime_cycles(edges, modules):
        yield f"    frozenset({sorted(component)!r}),"
    yield ")"
    yield "UNREACHABLE_MODULE_BASELINE = frozenset({"
    for name in sorted(unreachable_modules(edges, modules)):
        yield f"    {name!r},"
    yield "})"


if __name__ == "__main__":
    for rendered in iter_baseline_lines():
        print(rendered)
