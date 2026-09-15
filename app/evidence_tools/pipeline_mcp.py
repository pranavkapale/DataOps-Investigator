import asyncio
import contextlib
import json
import sys
import threading
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.evidence_tools.pipeline import (
    PipelineEvidenceProviderError,
    UnknownPipelineRunError,
    PipelineRunTelemetry,
    PipelineLogTelemetry,
    SchemaTelemetry,
)

class PipelineMCPEvidenceProvider:
    """An MCP-backed implementation of the PipelineEvidenceProvider protocol."""

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

    def __enter__(self) -> "PipelineMCPEvidenceProvider":
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
            raise PipelineEvidenceProviderError("MCP session is not connected. Ensure the provider is used within a context manager.")

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop
        )
        result = future.result()

        if not result.content:
            raise PipelineEvidenceProviderError("MCP tool returned no content")

        text = result.content[0].text
        data = json.loads(text)

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
