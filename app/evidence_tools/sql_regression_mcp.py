import json
import logging
from typing import Optional

from app.evidence_tools.sql_regression import (
    SQLEvidenceProvider,
    SQLQueryRun,
    SQLNode,
    UnknownSQLQueryError,
)
from app.mcp_tools.session import MCPStdioSession

logger = logging.getLogger(__name__)

class SQLMCPEvidenceProvider(SQLEvidenceProvider):
    def __init__(self, command: str = "python3", args: list[str] = ["-m", "app.mcp_server"]):
        self.session = MCPStdioSession(command, args)

    def __enter__(self):
        self.session.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.__exit__(exc_type, exc_val, exc_tb)

    def _call_tool(self, name: str, arguments: dict) -> dict:
        try:
            res_dict = self.session.call_tool_sync(name, arguments)
        except Exception as e:
            raise RuntimeError(f"MCP Tool Error ({name}): {e}")
        
        if "error" in res_dict:
            if "unknown" in res_dict["error"].lower() or "not found" in res_dict["error"].lower():
                raise UnknownSQLQueryError(res_dict["error"])
            raise RuntimeError(f"MCP Tool Logic Error ({name}): {res_dict['error']}")
        return res_dict
        
    def _parse_query(self, data: dict) -> SQLQueryRun:
        nodes = [SQLNode(**n) for n in data["nodes"]]
        return SQLQueryRun(
            query_id=data["query_id"],
            execution_time_ms=data["execution_time_ms"],
            nodes=nodes
        )

    def get_query(self, query_id: str) -> SQLQueryRun:
        data = self._call_tool("sql_get_query", {"query_id": query_id})
        return self._parse_query(data)

    def get_baseline_query(self) -> SQLQueryRun:
        data = self._call_tool("sql_get_baseline_query", {})
        return self._parse_query(data)
