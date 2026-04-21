from contextlib import contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Driver, Session
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class Neo4jClient:
    def __init__(self, uri: str = NEO4J_URI,
                 user: str = NEO4J_USER,
                 password: str = NEO4J_PASSWORD):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with self._driver.session() as s:
            yield s

    def verify_connectivity(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def run(self, query: str, **params) -> list[dict]:
        with self.session() as s:
            result = s.run(query, **params)
            return [dict(r) for r in result]

    def run_write(self, query: str, **params) -> None:
        with self.session() as s:
            s.run(query, **params)

    def create_constraints(self) -> None:
        """Create uniqueness constraints for all node types."""
        constraints = [
            "CREATE CONSTRAINT workbook_id IF NOT EXISTS FOR (w:Workbook) REQUIRE w.id IS UNIQUE",
            "CREATE CONSTRAINT sheet_id IF NOT EXISTS FOR (s:Sheet) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT cell_id IF NOT EXISTS FOR (c:Cell) REQUIRE c.id IS UNIQUE",
        ]
        with self.session() as s:
            for cql in constraints:
                s.run(cql)

    def clear_workbook(self, workbook_id: str) -> None:
        """Delete all nodes belonging to a workbook (for re-import)."""
        self.run_write(
            """
            MATCH (w:Workbook {id: $wid})
            OPTIONAL MATCH (w)-[:HAS_SHEET]->(sh:Sheet)
            OPTIONAL MATCH (sh)-[:HAS_SECTION]->(sec:Section)
            OPTIONAL MATCH (sec)-[:CONTAINS_CELL]->(c:Cell)
            DETACH DELETE w, sh, sec, c
            """,
            wid=workbook_id,
        )
