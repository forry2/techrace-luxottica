#!/usr/bin/env python3
"""Detects import cycles between modules of a Python package.

Parses every .py file under the package directory with `ast` instead of
importing it, and collects every `import` / `from ... import` statement at any
nesting level, including deferred imports inside function bodies. Tracing
imports at runtime would miss a cycle that only exists through a deferred
import, since that edge may never execute.

Usage:
    python3 detect_cycles.py <package_dir> <package_name> [--graph]

Default mode: prints "no cycles" and exits 0 if the import graph is acyclic;
otherwise prints each cycle (one per line) and exits 1.

--graph mode: prints the sorted adjacency list ("module -> dep1,dep2,...", one
module per line) and always exits 0. It hands the extracted dependency graph to
the LLM judge, which compares it against an architecture document.
"""
import ast
import sys
from pathlib import Path


def build_import_graph(package_dir, package_name):
    graph = {}
    package_dir = Path(package_dir)
    for py_file in package_dir.rglob("*.py"):
        rel = py_file.relative_to(package_dir.parent)
        module_name = ".".join(rel.with_suffix("").parts)
        if module_name.endswith(".__init__"):
            module_name = module_name[: -len(".__init__")]

        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    full = node.module if node.level == 0 else "." * node.level + node.module
                    imported.add(full)
                    # "from pkg import a" may import the submodule pkg.a rather than a
                    # name from pkg/__init__.py. Add the candidate; if it is not a real
                    # module it matches no graph node.
                    for alias in node.names:
                        imported.add(f"{full}.{alias.name}")

        local_imports = {
            m for m in imported if m == package_name or m.startswith(package_name + ".")
        }
        graph[module_name] = local_imports
    return graph


def find_cycles(graph):
    cycles = []
    visited = set()

    def dfs(node, path):
        if node in path:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        for neighbor in graph.get(node, ()):
            if neighbor in graph:
                dfs(neighbor, path + [node])

    for start in graph:
        dfs(start, [])
    return cycles


def main():
    if len(sys.argv) not in (3, 4):
        print("usage: detect_cycles.py <package_dir> <package_name> [--graph]", file=sys.stderr)
        return 2

    package_dir, package_name = sys.argv[1], sys.argv[2]
    graph_mode = len(sys.argv) == 4 and sys.argv[3] == "--graph"

    graph = build_import_graph(package_dir, package_name)

    if graph_mode:
        for module in sorted(graph):
            # Keep only edges to real modules: build_import_graph() also adds
            # speculative "pkg.name" candidates, mostly function/class names.
            real_deps = {dep for dep in graph[module] if dep in graph and dep != module}
            deps = ",".join(sorted(real_deps)) or "-"
            print(f"{module} -> {deps}")
        return 0

    cycles = find_cycles(graph)

    if not cycles:
        print("no cycles")
        return 0

    seen = set()
    for cycle in cycles:
        key = tuple(sorted(set(cycle)))
        if key in seen:
            continue
        seen.add(key)
        print(" -> ".join(cycle))
    return 1


if __name__ == "__main__":
    sys.exit(main())
