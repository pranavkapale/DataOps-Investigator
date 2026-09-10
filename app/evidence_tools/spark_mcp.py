import asyncio
import contextlib
import json
import sys
import threading
from typing import Any, Dict, Optional

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
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[contextlib.AsyncExitStack] = None
        self._ready_event = threading.Event()
        self._error: Optional[Exception] = None

    @property
    def scenario_dir(self) -> Any:
        from pathlib import Path
        return Path("mcp://remote-spark-provider")

    def __enter__(self) -> "SparkMCPEvidenceProvider":
        self._loop = asyncio.new_event_loop()
        self._ready_event.clear()
        self._error = None

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait()

        if self._error:
            self.__exit__(type(self._error), self._error, self._error.__traceback__)
            raise self._error

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._cleanup(), self._loop)
                future.result(timeout=5.0)
            except Exception:
                pass # Ignore cleanup errors
        if self._thread:
            self._thread.join(timeout=5.0)

        self._loop = None
        self._thread = None
        self._session = None
        self._exit_stack = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._setup())
            self._ready_event.set()
            self._loop.run_forever()
        except Exception as e:
            self._error = e
            self._ready_event.set()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    async def _setup(self) -> None:
        self._exit_stack = contextlib.AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(self.server_params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def _cleanup(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self._loop.stop()

    def _call_tool_sync(self, name: str, arguments: dict) -> Any:
        if not self._session or not self._loop or not self._loop.is_running():
            raise SparkEvidenceProviderError("MCP session is not connected. Ensure the provider is used within a context manager.")

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop
        )
        result = future.result()

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
