import asyncio
import contextlib
import json
import threading
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPStdioSession:
    """Helper for managing an MCP stdio subprocess, async loop, and session."""
    def __init__(self, command: str, args: list[str]):
        self.server_params = StdioServerParameters(command=command, args=args)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[contextlib.AsyncExitStack] = None
        self._ready_event = threading.Event()
        self._error: Optional[Exception] = None

    def __enter__(self) -> "MCPStdioSession":
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
                pass
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

    def call_tool_sync(self, name: str, arguments: dict) -> Any:
        if not self._session or not self._loop or not self._loop.is_running():
            raise RuntimeError("MCP session is not connected.")

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop
        )
        result = future.result()

        if not result.content:
            raise RuntimeError("MCP tool returned no content")

        text = result.content[0].text
        data = json.loads(text)
        return data
