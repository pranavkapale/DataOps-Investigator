import sys
from typing import Any

from app.evidence_tools.pipeline import (
    PipelineEvidenceProviderError,
    UnknownPipelineRunError,
    PipelineRunTelemetry,
    PipelineLogTelemetry,
    SchemaTelemetry,
)
from app.mcp_tools.session import MCPStdioSession


class PipelineMCPEvidenceProvider:
    """An MCP-backed implementation of the PipelineEvidenceProvider protocol."""

    def __init__(self, command: str = sys.executable, module: str = "app.mcp_server"):
        self.session = MCPStdioSession(command=command, args=["-m", module])

    def __enter__(self) -> "PipelineMCPEvidenceProvider":
        self.session.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.session.__exit__(exc_type, exc_val, exc_tb)

    def _call_tool_sync(self, name: str, arguments: dict) -> Any:
        try:
            data = self.session.call_tool_sync(name, arguments)
        except RuntimeError as e:
            raise PipelineEvidenceProviderError(str(e))

        if isinstance(data, dict) and "error" in data:
            err_msg = data["error"]
            if "Unknown run ID" in err_msg or "UnknownPipelineRunError" in err_msg:
                raise UnknownPipelineRunError(err_msg)
            raise PipelineEvidenceProviderError(err_msg)
        return data

    def get_run(self, run_id: str) -> PipelineRunTelemetry:
        data = self._call_tool_sync("pipeline_get_run", {"run_id": run_id})
        return PipelineRunTelemetry.model_validate(data)

    def get_logs(self, run_id: str, task_id: str) -> PipelineLogTelemetry:
        data = self._call_tool_sync("pipeline_get_logs", {"run_id": run_id, "task_id": task_id})
        return PipelineLogTelemetry.model_validate(data)

    def get_current_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        data = self._call_tool_sync("pipeline_get_current_schema", {"dataset_id": dataset_id, "table_id": table_id})
        return SchemaTelemetry.model_validate(data)

    def get_baseline_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        data = self._call_tool_sync("pipeline_get_baseline_schema", {"dataset_id": dataset_id, "table_id": table_id})
        return SchemaTelemetry.model_validate(data)
