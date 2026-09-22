import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class UnknownSQLQueryError(Exception):
    pass

@dataclass
class SQLNode:
    node_id: int
    type: str
    input_rows_left: int
    input_rows_right: int
    output_rows: int
    join_type: str

@dataclass
class SQLQueryRun:
    query_id: str
    execution_time_ms: int
    nodes: List[SQLNode]

class SQLEvidenceProvider(ABC):
    @abstractmethod
    def get_query(self, query_id: str) -> SQLQueryRun:
        pass
    
    @abstractmethod
    def get_baseline_query(self) -> SQLQueryRun:
        pass

class SQLFixtureEvidenceProvider(SQLEvidenceProvider):
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            self.data_dir = Path(__file__).resolve().parent.parent.parent / "scenarios" / "sql_regression"
        else:
            self.data_dir = Path(data_dir)
            
    def _load_run(self, path: Path) -> SQLQueryRun:
        if not path.exists():
            raise UnknownSQLQueryError(f"Fixture not found: {path}")
        try:
            with open(path, "r") as f:
                data = json.load(f)
            nodes = [SQLNode(**n) for n in data["nodes"]]
            return SQLQueryRun(
                query_id=data["query_id"],
                execution_time_ms=data["execution_time_ms"],
                nodes=nodes
            )
        except Exception as e:
            logger.error(f"Error loading fixture {path}: {e}")
            raise

    def get_query(self, query_id: str) -> SQLQueryRun:
        if query_id != "sql-run-2026-09-20":
            if query_id == "sql-query-101":
                pass # Accept the one passed from tests/cli
            else:
                raise UnknownSQLQueryError(f"Unknown query ID: {query_id}")
        # In this mock, we just load the incident run
        path = self.data_dir / "incident" / "query.json"
        return self._load_run(path)

    def get_baseline_query(self) -> SQLQueryRun:
        path = self.data_dir / "baseline" / "query.json"
        return self._load_run(path)
