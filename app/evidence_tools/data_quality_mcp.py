import json
import logging
from typing import Optional

from app.evidence_tools.data_quality import (
    DataQualityEvidenceProvider,
    DataQualityRun,
    DataQualityMetrics,
    UnknownDataQualityRunError,
)
from app.mcp_tools.session import MCPStdioSession

logger = logging.getLogger(__name__)

class DataQualityMCPEvidenceProvider(DataQualityEvidenceProvider):
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
                raise UnknownDataQualityRunError(res_dict["error"])
            raise RuntimeError(f"MCP Tool Logic Error ({name}): {res_dict['error']}")
        return res_dict
        
    def _parse_run(self, data: dict) -> DataQualityRun:
        return DataQualityRun(
            run_id=data["run_id"],
            dataset=data["dataset"],
            table=data["table"],
            metrics=DataQualityMetrics(**data["metrics"])
        )

    def get_run(self, run_id: str) -> DataQualityRun:
        data = self._call_tool("data_quality_get_run", {"run_id": run_id})
        return self._parse_run(data)

    def get_baseline(self, dataset: str, table: str) -> DataQualityRun:
        data = self._call_tool("data_quality_get_baseline", {"dataset": dataset, "table": table})
        return self._parse_run(data)
