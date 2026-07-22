"""MCP Client for connecting to the Feishu MCP server via SSE transport."""

from __future__ import annotations

import json
import httpx
from dataclasses import dataclass


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict


class MCPClient:
    """Minimal MCP SSE client that handles the Spring WebMvc MCP transport."""

    def __init__(self, base_url: str = "http://mcppage.ruijie.com.cn:9810/mcp"):
        self.base_url = base_url
        self.session_id: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._tools: list[MCPTool] = []
        self._sse_stream = None

    async def connect(self) -> list[MCPTool]:
        self._client = httpx.AsyncClient(timeout=30)
        # Step 1: Initialize
        init_body = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "digital-twin", "version": "2.0"},
            },
            "id": 1,
        }
        resp = await self._client.post(
            self.base_url,
            json=init_body,
            headers={"Accept": "application/json, text/event-stream"},
        )
        resp.raise_for_status()
        self.session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("No session ID returned from MCP server")

        # Step 2: Establish SSE stream to receive responses
        self._sse_stream = await self._open_sse()

        # Step 3: List tools
        tools = await self._call("tools/list")
        self._tools = []
        if tools and "tools" in tools:
            for t in tools["tools"]:
                self._tools.append(MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                ))
        return self._tools

    async def _open_sse(self):
        """Open SSE stream for receiving MCP responses."""
        return await self._client.stream(
            "GET",
            self.base_url,
            headers={
                "Accept": "text/event-stream",
                "Mcp-Session-Id": self.session_id,
            },
        )

    async def _call(self, method: str, params: dict | None = None) -> dict:
        """Call an MCP method and get the response via SSE."""
        call_id = hash(method + str(params)) % 10000
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": call_id,
        }

        # Send request
        await self._client.post(
            self.base_url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": self.session_id,
            },
        )

        # Read response from SSE stream
        # The response comes through the SSE stream as a JSON-RPC message
        async for line in self._sse_stream.aiter_lines():
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                if data.get("id") == call_id:
                    if "error" in data:
                        raise RuntimeError(f"MCP error: {data['error']}")
                    return data.get("result", {})

        return {}

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        return await self._call("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

    async def close(self):
        if self._sse_stream:
            await self._sse_stream.aclose()
        if self._client:
            await self._client.aclose()

    async def list_tools(self) -> list[MCPTool]:
        return self._tools


# Test helper
async def test_mcp():
    client = MCPClient()
    try:
        tools = await client.connect()
        print(f"Connected! {len(tools)} tools available:")
        for t in tools:
            print(f"  - {t.name}: {t.description[:80]}...")
    finally:
        await client.close()
