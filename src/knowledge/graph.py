"""Knowledge Graph — index relationnel SQLite.

Stocke les relations entre concepts, entités, et sessions.
Utilisé par ProactiveEngine pour détecter les patterns.
Optimisé M1 8 Go : SQLite pur (0 RAM additionnelle en idle).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".nuru" / "knowledge.db"


@dataclass
class Node:
    """Nœud du graphe de connaissances."""
    id: int = 0
    label: str = ""
    entity_type: str = "concept"
    metadata: dict = field(default_factory=dict)
    weight: float = 1.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.entity_type,
            "metadata": self.metadata,
            "weight": self.weight,
        }


@dataclass
class Edge:
    """Relation entre deux nœuds."""
    id: int = 0
    source_id: int = 0
    target_id: int = 0
    relation: str = ""
    weight: float = 1.0
    created_at: float = 0.0


class KnowledgeGraph:
    """Graphe de connaissances persistant (SQLite).

    Usage :
        kg = KnowledgeGraph()
        kg.init()
        node = kg.add_node("NURU", "concept")
        project = kg.add_node("V9", "project")
        kg.add_edge(node.id, project.id, "implements")
        related = kg.find_related("NURU")
        kg.close()
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    def init(self) -> None:
        """Initialise la base et crée les tables si besoin."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL DEFAULT 'concept',
                metadata TEXT DEFAULT '{}',
                weight REAL DEFAULT 1.0,
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'related_to',
                weight REAL DEFAULT 1.0,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(entity_type);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
        """)
        self._conn.commit()
        logger.info(f"Knowledge Graph prêt: {self.db_path}")

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("KnowledgeGraph non initialisé. Appelez init() d'abord.")
        return self._conn

    def add_node(self, label: str, entity_type: str = "concept",
                 metadata: Optional[dict] = None, weight: float = 1.0) -> Node:
        """Ajoute ou met à jour un nœud."""
        conn = self._ensure_conn()
        cursor = conn.execute("SELECT * FROM nodes WHERE label = ?", (label,))
        existing = cursor.fetchone()

        now = time.time()
        meta_json = json.dumps(metadata or {})

        if existing:
            conn.execute(
                "UPDATE nodes SET weight = ?, metadata = ?, updated_at = ? WHERE id = ?",
                (weight, meta_json, now, existing["id"]),
            )
            node_id = int(existing["id"])
        else:
            cursor = conn.execute(
                "INSERT INTO nodes (label, entity_type, metadata, weight, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (label, entity_type, meta_json, weight, now, now),
            )
            node_id = int(cursor.lastrowid) if cursor.lastrowid else 0

        conn.commit()
        return Node(
            id=node_id, label=label, entity_type=entity_type,
            metadata=metadata or {}, weight=weight,
            created_at=existing["created_at"] if existing else now,
            updated_at=now,
        )

    def add_edge(self, source_id: int, target_id: int, relation: str = "related_to",
                 weight: float = 1.0) -> Edge:
        """Ajoute une arête entre deux nœuds."""
        conn = self._ensure_conn()
        cursor = conn.execute(
            "INSERT INTO edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
            (source_id, target_id, relation, weight),
        )
        conn.commit()
        eid = int(cursor.lastrowid) if cursor.lastrowid else 0
        return Edge(
            id=eid, source_id=source_id, target_id=target_id,
            relation=relation, weight=weight, created_at=time.time(),
        )

    def find_related(self, label: str, relation: Optional[str] = None,
                     max_results: int = 10) -> list[Node]:
        """Trouve les nœuds reliés à un label donné."""
        conn = self._ensure_conn()
        query = """
            SELECT DISTINCT n.*, e.relation as edge_relation, e.weight as edge_weight
            FROM nodes n
            JOIN edges e ON (n.id = e.target_id OR n.id = e.source_id)
            JOIN nodes src ON (src.id = e.source_id OR src.id = e.target_id)
            WHERE src.label = ? AND n.label != ?
        """
        params = [label, label]

        if relation:
            query += " AND e.relation = ?"
            params.append(relation)

        query += f" ORDER BY e.weight DESC LIMIT {max_results}"

        rows = conn.execute(query, params).fetchall()
        return [
            Node(
                id=int(r["id"]), label=r["label"], entity_type=r["entity_type"],
                metadata=json.loads(r["metadata"] or "{}"),
                weight=float(r["weight"]) * float(r["edge_weight"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ) for r in rows
        ]

    def search_nodes(self, query: str, entity_type: Optional[str] = None,
                     limit: int = 20) -> list[Node]:
        """Recherche des nœuds par label."""
        conn = self._ensure_conn()
        sql = "SELECT * FROM nodes WHERE label LIKE ?"
        params = [f"%{query}%"]

        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)

        sql += f" ORDER BY weight DESC LIMIT {limit}"

        rows = conn.execute(sql, params).fetchall()
        return [
            Node(
                id=int(r["id"]), label=r["label"], entity_type=r["entity_type"],
                metadata=json.loads(r["metadata"] or "{}"),
                weight=float(r["weight"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ) for r in rows
        ]

    def get_stats(self) -> dict:
        """Statistiques du graphe."""
        conn = self._ensure_conn()
        total_nodes = int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])
        total_edges = int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
        types = conn.execute(
            "SELECT entity_type, COUNT(*) as c FROM nodes GROUP BY entity_type"
        ).fetchall()
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "by_type": {r["entity_type"]: int(r["c"]) for r in types},
        }

    def close(self) -> None:
        """Ferme la connexion."""
        if self._conn:
            self._conn.close()
            self._conn = None
