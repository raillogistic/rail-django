"""
Dependency graph utilities for Form API.
"""

from __future__ import annotations

from typing import Iterable, Mapping


def detect_cycles(nodes: Iterable[str] | Mapping[str, Iterable[str]]) -> bool:
    if isinstance(nodes, Mapping):
        graph = {
            str(node): [str(dep) for dep in deps or []]
            for node, deps in nodes.items()
        }
    else:
        graph = {str(node): [] for node in nodes}

    visiting: set[str] = set()
    visited: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True

        visiting.add(node)
        for dep in graph.get(node, []):
            if _dfs(dep):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for node in graph:
        if _dfs(node):
            return True
    return False
