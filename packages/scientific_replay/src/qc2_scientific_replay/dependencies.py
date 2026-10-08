"""Dependency DAG validation and deterministic transitive closure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import ReplayError


def resolve_dependency_closure(
    nodes: Sequence[Mapping[str, object]],
    roots: Sequence[str],
    *,
    max_depth: int,
) -> tuple[str, ...]:
    """Validate the full DAG and return root-reachable nodes in dependency order."""
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth <= 0:
        raise ValueError("max_depth must be a positive integer")
    node_map: dict[str, Mapping[str, object]] = {}
    for node in nodes:
        node_id = node.get("node_id")
        dependencies = node.get("depends_on")
        if not isinstance(node_id, str) or not node_id:
            raise ReplayError("dependency graph contains a node without a node_id")
        if node_id in node_map:
            raise ReplayError(f"dependency graph repeats node {node_id}")
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise ReplayError(f"dependency graph has invalid dependencies for {node_id}")
        if len(set(dependencies)) != len(dependencies):
            raise ReplayError(f"dependency graph repeats an edge from {node_id}")
        node_map[node_id] = node

    if not roots or any(not isinstance(root, str) or root not in node_map for root in roots):
        raise ReplayError("dependency graph has a missing or invalid root")
    if len(set(roots)) != len(roots):
        raise ReplayError("dependency graph repeats a root")
    for node_id, node in node_map.items():
        for dependency in node["depends_on"]:  # type: ignore[index]
            if dependency not in node_map:
                raise ReplayError(f"missing dependency {dependency} referenced by {node_id}")

    state: dict[str, int] = {}
    ordered: list[str] = []
    reachable: set[str] = set()

    def visit(node_id: str, depth: int) -> None:
        if depth > max_depth:
            raise ReplayError(f"dependency depth exceeds limit at {node_id}")
        current = state.get(node_id, 0)
        if current == 1:
            raise ReplayError(f"dependency cycle detected at {node_id}")
        if current == 2:
            reachable.add(node_id)
            return
        state[node_id] = 1
        for dependency in sorted(
            node_map[node_id]["depends_on"], key=lambda value: value.encode("utf-8")  # type: ignore[index,union-attr]
        ):
            visit(dependency, depth + 1)
        state[node_id] = 2
        reachable.add(node_id)
        ordered.append(node_id)

    for root in roots:
        visit(root, 1)
    return tuple(ordered)
