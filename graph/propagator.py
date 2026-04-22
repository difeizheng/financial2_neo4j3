"""Change propagation engine using topological sort.

When one or more cell values change, this module:
1. Finds all downstream cells (those that DEPEND_ON the changed cells, transitively).
2. Topologically sorts them so each cell is recalculated after its dependencies.
3. Recalculates each cell using CalcEngine.
4. Writes updated values back to Neo4j.
"""
from collections import deque
from typing import Any

from engine.calc_engine import CalcEngine
from graph.neo4j_client import Neo4jClient


class Propagator:
    def __init__(self, client: Neo4jClient):
        self._client = client
        self._engine = CalcEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propagate(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply value changes and propagate through the dependency graph.

        changes: {cell_id: new_value}
        Returns: {cell_id: new_value} for every cell that was updated
                 (including the seed changes themselves).
        """
        if not changes:
            return {}

        # 1. Collect all downstream cells (BFS over reverse DEPENDS_ON edges)
        downstream = self._find_downstream(list(changes.keys()))

        # 2. Build local subgraph for topological sort
        subgraph = self._fetch_subgraph(list(changes.keys()) + list(downstream))

        # 3. Topological sort
        order = self._topo_sort(subgraph)

        # 4. Fetch current values for all cells in scope
        all_ids = list(subgraph.keys())
        cell_values = self._fetch_values(all_ids)

        # Apply seed changes
        cell_values.update(changes)

        # 5. Recalculate in order
        updated: dict[str, Any] = dict(changes)
        for cell_id in order:
            if cell_id in changes:
                continue  # already set by user
            formula, sheet = self._fetch_formula(cell_id)
            if not formula:
                continue
            new_val = self._engine.evaluate(formula, cell_values, sheet)
            if new_val is not None and new_val != cell_values.get(cell_id):
                cell_values[cell_id] = new_val
                updated[cell_id] = new_val

        # 6. Write back to Neo4j
        if updated:
            self._write_values(updated)

        return updated

    def dry_run_with_comparison(self, changes: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Simulate propagation without writing to Neo4j.

        Returns: {cell_id: {"old": old_value, "new": new_value, "formula": formula_raw}}
        """
        if not changes:
            return {}

        downstream = self._find_downstream(list(changes.keys()))
        subgraph = self._fetch_subgraph(list(changes.keys()) + list(downstream))
        order = self._topo_sort(subgraph)

        all_ids = list(subgraph.keys())
        cell_values = self._fetch_values(all_ids)
        old_values = dict(cell_values)

        cell_values.update(changes)

        updated: dict[str, Any] = dict(changes)
        for cell_id in order:
            if cell_id in changes:
                continue
            formula, sheet = self._fetch_formula(cell_id)
            if not formula:
                continue
            new_val = self._engine.evaluate(formula, cell_values, sheet)
            if new_val is not None and new_val != cell_values.get(cell_id):
                cell_values[cell_id] = new_val
                updated[cell_id] = new_val

        result: dict[str, dict[str, Any]] = {}
        for cid, new_val in updated.items():
            formula, _ = self._fetch_formula(cid)
            result[cid] = {
                "old": old_values.get(cid),
                "new": new_val,
                "formula": formula,
            }
        return result

    def propagate_with_trace(self, changes: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Apply changes and return (updated_values, topo_order)."""
        if not changes:
            return {}, []

        downstream = self._find_downstream(list(changes.keys()))
        subgraph = self._fetch_subgraph(list(changes.keys()) + list(downstream))
        order = self._topo_sort(subgraph)

        all_ids = list(subgraph.keys())
        cell_values = self._fetch_values(all_ids)
        cell_values.update(changes)

        updated: dict[str, Any] = dict(changes)
        for cell_id in order:
            if cell_id in changes:
                continue
            formula, sheet = self._fetch_formula(cell_id)
            if not formula:
                continue
            new_val = self._engine.evaluate(formula, cell_values, sheet)
            if new_val is not None and new_val != cell_values.get(cell_id):
                cell_values[cell_id] = new_val
                updated[cell_id] = new_val

        if updated:
            self._write_values(updated)

        return updated, order

    # ------------------------------------------------------------------
    # Graph traversal helpers
    # ------------------------------------------------------------------

    def _find_downstream(self, seed_ids: list[str]) -> set[str]:
        """BFS: find all cells that (transitively) depend on seed_ids."""
        visited: set[str] = set()
        queue = deque(seed_ids)
        while queue:
            cid = queue.popleft()
            if cid in visited:
                continue
            visited.add(cid)
            # Cells that DEPEND_ON cid (i.e. cid is in their formula_refs)
            rows = self._client.run(
                "MATCH (c:Cell)-[:DEPENDS_ON]->(:Cell {id: $id}) RETURN c.id AS id",
                id=cid,
            )
            for r in rows:
                if r["id"] not in visited:
                    queue.append(r["id"])
        # Exclude the seeds themselves
        return visited - set(seed_ids)

    def _fetch_subgraph(self, cell_ids: list[str]) -> dict[str, list[str]]:
        """Return adjacency: {cell_id: [dep_cell_id, ...]} for the given ids."""
        if not cell_ids:
            return {}
        rows = self._client.run(
            """
            MATCH (c:Cell)-[:DEPENDS_ON]->(dep:Cell)
            WHERE c.id IN $ids
            RETURN c.id AS src, dep.id AS tgt
            """,
            ids=cell_ids,
        )
        graph: dict[str, list[str]] = {cid: [] for cid in cell_ids}
        for r in rows:
            if r["src"] in graph:
                graph[r["src"]].append(r["tgt"])
        return graph

    def _topo_sort(self, graph: dict[str, list[str]]) -> list[str]:
        """Kahn's algorithm topological sort. graph: {node: [dependencies]}."""
        # Rebuild: reverse edges so we can do Kahn's properly
        # in_degree[n] = number of dependencies of n that are in the subgraph
        in_deg: dict[str, int] = {n: 0 for n in graph}
        rev: dict[str, list[str]] = {n: [] for n in graph}
        for node, deps in graph.items():
            for d in deps:
                if d in graph:
                    in_deg[node] += 1
                    rev[d].append(node)

        queue = deque(n for n, d in in_deg.items() if d == 0)
        order: list[str] = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for downstream in rev.get(n, []):
                in_deg[downstream] -= 1
                if in_deg[downstream] == 0:
                    queue.append(downstream)
        return order

    # ------------------------------------------------------------------
    # Neo4j read/write helpers
    # ------------------------------------------------------------------

    def _fetch_values(self, cell_ids: list[str]) -> dict[str, Any]:
        if not cell_ids:
            return {}
        rows = self._client.run(
            "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.value AS value",
            ids=cell_ids,
        )
        return {r["id"]: r["value"] for r in rows}

    def _fetch_formula(self, cell_id: str) -> tuple[str | None, str]:
        rows = self._client.run(
            "MATCH (c:Cell {id: $id}) RETURN c.formula_raw AS formula, c.sheet AS sheet",
            id=cell_id,
        )
        if rows:
            return rows[0]["formula"], rows[0]["sheet"]
        return None, ""

    def _write_values(self, updates: dict[str, Any]) -> None:
        rows = [{"id": k, "value": v} for k, v in updates.items()]
        for i in range(0, len(rows), 500):
            self._client.run_write(
                """
                UNWIND $rows AS row
                MATCH (c:Cell {id: row.id})
                SET c.value = row.value
                """,
                rows=rows[i:i + 500],
            )
