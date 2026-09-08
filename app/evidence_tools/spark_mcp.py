import asyncio
import json
import sys
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.evidence_tools.spark import (
    SparkEvidenceProviderError,
    SparkJobTelemetry,
    SparkPartitionStatistics,
    SparkRunTelemetry,
    SparkStagesTelemetry,
    UnknownSparkRunError,
)

class SparkMCPEvidenceProvider:
    """An MCP-backed implementation of the SparkEvidenceProvider protocol."""
    
    def __init__(self, command: str = sys.executable, module: str = "app.mcp_server"):
        self.server_params = StdioServerParameters(
            command=command,
            args=["-m", module]
        )

    @property
    def scenario_dir(self) -> Any:
        from pathlib import Path
        return Path("mcp://remote-spark-provider")

    def _call_tool_sync(self, name: str, arguments: dict) -> Any:
        async def run():
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    
                    if not result.content:
                        raise SparkEvidenceProviderError("MCP tool returned no content")
                        
                    text = result.content[0].text
                    data = json.loads(text)
                    
                    if isinstance(data, dict) and "error" in data:
                        err_msg = data["error"]
                        if "was not found" in err_msg or "UnknownSparkRunError" in err_msg:
                            raise UnknownSparkRunError(err_msg)
                        raise SparkEvidenceProviderError(err_msg)
                    return data
        
        return asyncio.run(run())

    def get_job(self, run_id: str) -> SparkJobTelemetry:
        data = self._call_tool_sync("spark_get_job", {"run_id": run_id})
        return SparkJobTelemetry.model_validate(data)

    def get_run(self, run_id: str) -> SparkRunTelemetry:
        data = self._call_tool_sync("spark_get_run", {"run_id": run_id})
        return SparkRunTelemetry.model_validate(data)

    def get_stages(self, run_id: str) -> SparkStagesTelemetry:
        data = self._call_tool_sync("spark_get_stages", {"run_id": run_id})
        return SparkStagesTelemetry.model_validate(data)

    def get_partition_statistics(self, run_id: str) -> SparkPartitionStatistics:
        data = self._call_tool_sync("spark_get_partition_statistics", {"run_id": run_id})
        return SparkPartitionStatistics.model_validate(data)

    def get_configuration(self, run_id: str) -> Dict[str, str]:
        data = self._call_tool_sync("spark_get_configuration", {"run_id": run_id})
        return data

    def get_baseline(self, job_id: str, run_id: str) -> SparkRunTelemetry:
        data = self._call_tool_sync("spark_get_baseline", {"job_id": job_id, "run_id": run_id})
        return SparkRunTelemetry.model_validate(data)
