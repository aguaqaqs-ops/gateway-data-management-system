"""Backend import-boundary rules used by ``tests/test_architecture.py``.

The rules encode the P5 §2A.2 guardrails as precise module/symbol checks. Existing violations are
frozen in ``tests/architecture_baseline.py``; ``test_architecture.py`` fails on any new violation
and on any baseline entry that no longer occurs, so the baseline can only shrink.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"
BACKEND_PACKAGE = "gateway_backend"
PRODUCTION_ENTRYPOINTS = (
    "gateway_backend.app",
    "gateway_backend.bootstrap.http_server",
    "gateway_backend.bootstrap.operation_worker",
)
# Package-root modules that belong to process composition rather than to an unowned bucket.
COMPOSITION_MODULES = frozenset(
    {"gateway_backend", "gateway_backend.app", "gateway_backend.settings"}
)

RULE_LAYER = "layer"
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
    "capabilities": frozenset(),
    "capability": frozenset({ANY_CAPABILITY, "artifacts"}),
    "capability:canonical_row_hash": frozenset({ANY_CAPABILITY, "artifacts", "ext:compute"}),
    "cache": frozenset({"cache", "artifacts", ANY_CAPABILITY}),
    "application": frozenset({"application", "domain", "operations", "artifacts", ANY_CAPABILITY}),
    "http": frozenset({"http", "application", "domain", "operations", "artifacts", "ext:web"}),
    "infrastructure:control_db": frozenset(
        {ANY_INFRASTRUCTURE, "domain", "operations", "artifacts", APPLICATION_PORTS, "ext:sqlite"}
    ),
    "infrastructure:artifact_store": frozenset({ANY_INFRASTRUCTURE, "domain", "artifacts"}),
    "infrastructure:repository_read": _REPOSITORY_ADAPTER_EDGES,
    "infrastructure:repository_write": _REPOSITORY_ADAPTER_EDGES,
}
COMPOSITION_ZONES = frozenset({"composition", "bootstrap"})


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source: str
    target: str
    names: tuple[str, ...]
    context: str  # "module" | "function" | "type_checking"
    path: Path
    line: int


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
        location = f"{self.path.relative_to(BACKEND_SRC.parent)}:{self.line}"
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
        self._type_checking_depth = 0
        self.edges: list[ImportEdge] = []

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
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(alias.name, (), node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        names = tuple(alias.name for alias in node.names)
        if node.level == 0:
            assert node.module is not None
            self._add_from(node.module, names, node.lineno)
            return
        parts = self._source.split(".")
        if not self._is_init:
            parts = parts[:-1]
        if node.level > 1:
            parts = parts[: -(node.level - 1)]
        base = ".".join([*parts, *node.module.split(".")]) if node.module else ".".join(parts)
        self._add_from(base, names, node.lineno)

    def _add_from(self, base: str, names: tuple[str, ...], line: int) -> None:
        # ``from pkg import submodule`` targets the submodule; remaining names target ``pkg``.
        attribute_names: list[str] = []
        for name in names:
            candidate = f"{base}.{name}"
            if candidate in self._modules:
                self._add(candidate, (), line)
            else:
                attribute_names.append(name)
        if attribute_names or not names:
            self._add(base, tuple(attribute_names), line)

    def _add(self, target: str, names: tuple[str, ...], line: int) -> None:
        if target == "__future__":
            return
        self.edges.append(
            ImportEdge(self._source, target, names, self._context(), self._path, line)
        )


def collect_edges(modules: dict[str, Path] | None = None) -> list[ImportEdge]:
    known = modules if modules is not None else backend_modules()
    edges: list[ImportEdge] = []
    for path in backend_sources():
        source, is_init = module_name(path)
        visitor = _ImportVisitor(source, is_init, path, known)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        edges.extend(visitor.edges)
    return edges


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


def classify_edge(edge: ImportEdge, packages: frozenset[str]) -> tuple[str, str] | None:
    """Return the first rule an edge breaks, as ``(rule, target)``.

    Precedence: an edge that must not exist at all (layer) is reported once; otherwise private
    access, then non-public capability modules, then contracts importing their own execution code.
    """

    source_zone = zone(edge.source, packages)
    target_zone = zone(edge.target, packages)
    if source_zone is None or source_zone == "root":
        # Unowned root modules are reported once by RULE_UNOWNED_ROOT.
        return None

    if target_zone in _FORBIDDEN_EVERYWHERE:
        return (RULE_LAYER, edge.target)
    if (
        target_zone is not None
        and target_zone != "shared_kernel"
        and target_zone != source_zone
        and source_zone not in COMPOSITION_ZONES
    ):
        allowed_key = source_zone if source_zone in ALLOWED_ZONE_EDGES else (
            "capability" if source_zone.startswith("capability:") else source_zone
        )
        allowed = ALLOWED_ZONE_EDGES.get(allowed_key, frozenset())
        if not _target_category_allowed(allowed, target_zone, edge.target):
            return (RULE_LAYER, edge.target)

    if edge.target.startswith(f"{BACKEND_PACKAGE}."):
        private_owner = _private_owner(edge.target)
        if private_owner is not None and not _within(edge.source, private_owner):
            return (RULE_PRIVATE, edge.target)
        name_owner = edge.target if edge.target in packages else edge.target.rsplit(".", 1)[0]
        if not _within(edge.source, name_owner):
            private_names = sorted(name for name in edge.names if _is_private_name(name))
            if private_names:
                return (RULE_PRIVATE, f"{edge.target}:{','.join(private_names)}")

    if target_zone is not None and target_zone.startswith("capability:"):
        owner_package = ".".join(edge.target.split(".")[:3])
        public_modules = {owner_package, f"{owner_package}.contracts"}
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
    violations = [
        Violation(RULE_UNOWNED_ROOT, module, "", path, 1)
        for module, path in modules.items()
        if zone(module, packages) == "root"
    ]
    for edge in edges:
        found = classify_edge(edge, packages)
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

    Facade (``__init__``) re-exports do not count as use: an import of a facade symbol is resolved
    to the module that defines it.
    """

    edge_list = list(edges)
    reexports: dict[str, dict[str, str]] = defaultdict(dict)
    for edge in edge_list:
        if modules.get(edge.source, Path()).name != "__init__.py" or edge.target not in modules:
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

    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edge_list:
        if edge.context == "type_checking":
            continue
        source_is_init = modules.get(edge.source, Path()).name == "__init__.py"
        if source_is_init and edge.context != "function":
            continue
        if source_is_init and edge.context == "function":
            if edge.target not in modules:
                continue
            if edge.names and edge.target in reexports:
                for name in edge.names:
                    _add_edge(edge.source, resolve(edge.target, name))
            else:
                _add_edge(edge.source, edge.target)
            continue
        if edge.target not in modules:
            continue
        if edge.names and edge.target in reexports:
            for name in edge.names:
                _add_edge(edge.source, resolve(edge.target, name))
        else:
            _add_edge(edge.source, edge.target)

    def _mark_package_facades(seed: set[str], roots: Iterable[str]) -> list[str]:
        added: list[str] = []
        pending_mark = list(roots)
        while pending_mark:
            current = pending_mark.pop()
            parts = current.split(".")
            for index in range(len(parts) - 1, 1, -1):
                package = ".".join(parts[:index])
                init_path = modules.get(package)
                if init_path is None or init_path.name != "__init__.py":
                    continue
                if package not in seed:
                    seed.add(package)
                    added.append(package)
                    pending_mark.append(package)
        return added

    reached = set(PRODUCTION_ENTRYPOINTS)
    pending = list(reached)
    pending.extend(_mark_package_facades(reached, PRODUCTION_ENTRYPOINTS))
    while pending:
        current = pending.pop()
        for target in graph.get(current, ()):
            if target not in reached:
                reached.add(target)
                pending.append(target)
        pending.extend(_mark_package_facades(reached, [current]))
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
