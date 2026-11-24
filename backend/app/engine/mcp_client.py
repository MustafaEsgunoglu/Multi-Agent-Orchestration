"""Native MCP (SSE & stdio) client and dynamic OpenAPI/Swagger-to-Tool converter."""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

import httpx

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


@dataclass(frozen=True, slots=True)
class DynamicToolSpec:
    """Normalized tool definition produced from either an MCP server or an OpenAPI spec."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    source_kind: Literal["mcp", "openapi"]
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_openapi_spec(
    spec: dict[str, Any],
    *,
    base_url: str | None = None,
) -> list[DynamicToolSpec]:
    """Convert an OpenAPI 3.x / Swagger 2.x JSON schema into callable DynamicToolSpecs."""
    resolved_base = base_url
    if not resolved_base:
        servers = spec.get("servers") or []
        if servers and isinstance(servers[0], dict):
            resolved_base = str(servers[0].get("url", "")).rstrip("/")
        elif spec.get("host"):
            schemes = spec.get("schemes") or ["https"]
            base_path = spec.get("basePath", "")
            resolved_base = f"{schemes[0]}://{spec['host']}{base_path}".rstrip("/")
        else:
            resolved_base = ""

    tools: list[DynamicToolSpec] = []
    paths = spec.get("paths") or {}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue

            op_id = operation.get("operationId") or f"{method}_{path.strip('/').replace('/', '_')}"
            op_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(op_id))
            description = str(
                operation.get("summary") or operation.get("description") or f"{method.upper()} {path}"
            )

            properties: dict[str, Any] = {}
            required: list[str] = []
            path_params: list[str] = []
            query_params: list[str] = []

            for param in operation.get("parameters") or []:
                if not isinstance(param, dict) or not param.get("name"):
                    continue
                p_name = str(param["name"])
                p_in = str(param.get("in", "query"))
                p_schema = param.get("schema") or {"type": "string"}
                properties[p_name] = {
                    **p_schema,
                    "description": str(param.get("description", "")),
                }
                if param.get("required"):
                    required.append(p_name)
                if p_in == "path":
                    path_params.append(p_name)
                elif p_in == "query":
                    query_params.append(p_name)

            request_body = operation.get("requestBody")
            has_json_body = False
            if isinstance(request_body, dict):
                json_content = (request_body.get("content") or {}).get("application/json")
                if isinstance(json_content, dict) and isinstance(json_content.get("schema"), dict):
                    has_json_body = True
                    properties["body"] = json_content["schema"]
                    if request_body.get("required"):
                        required.append("body")

            tools.append(
                DynamicToolSpec(
                    name=op_name,
                    description=description,
                    parameters_schema={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                    source_kind="openapi",
                    metadata={
                        "method": method.upper(),
                        "path": path,
                        "base_url": resolved_base,
                        "path_params": path_params,
                        "query_params": query_params,
                        "has_json_body": has_json_body,
                    },
                )
            )

    return tools


async def invoke_openapi_tool(
    tool: DynamicToolSpec,
    arguments: dict[str, Any],
    *,
    auth_headers: dict[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute a converted OpenAPI tool with path/query/body mapping."""
    if tool.source_kind != "openapi":
        raise ValueError("invoke_openapi_tool requires an OpenAPI DynamicToolSpec.")

    meta = tool.metadata
    path = str(meta["path"])
    for p_name in meta.get("path_params", []):
        if p_name not in arguments:
            raise ValueError(f"Missing required path parameter '{p_name}'.")
        path = path.replace(f"{{{p_name}}}", str(arguments[p_name]))

    base_url = str(meta.get("base_url", "")).rstrip("/")
    url = f"{base_url}{path}"
    query = {k: arguments[k] for k in meta.get("query_params", []) if k in arguments}
    json_body = arguments.get("body") if meta.get("has_json_body") else None
    headers = dict(auth_headers or {})

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await client.request(
            method=str(meta["method"]),
            url=url,
            params=query or None,
            json=json_body,
            headers=headers,
        )
        content_type = response.headers.get("content-type", "")
        body: Any = (
            response.json() if "application/json" in content_type else response.text
        )
        return {
            "status_code": response.status_code,
            "ok": response.is_success,
            "output": body,
        }
    finally:
        if owns_client:
            await client.aclose()


class MCPClient:
    """Lightweight Model Context Protocol JSON-RPC 2.0 client (SSE/HTTP and stdio)."""

    def __init__(
        self,
        *,
        transport: Literal["sse", "stdio"],
        endpoint_or_command: str,
        auth_headers: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.transport = transport
        self.endpoint_or_command = endpoint_or_command
        self._auth_headers = dict(auth_headers or {})
        self._http_client = http_client
        self._timeout = timeout

    async def _rpc_sse(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self._auth_headers,
        }
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                self.endpoint_or_command,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = self._parse_json_or_sse_response(response)
            if "error" in data and data["error"] is not None:
                raise RuntimeError(f"MCP error: {data['error']}")
            return data.get("result", {})
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _parse_json_or_sse_response(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    raw = line[len("data:") :].strip()
                    if raw:
                        return json.loads(raw)
            return {}
        return response.json()

    async def _rpc_stdio(self, method: str, params: dict[str, Any] | None = None) -> Any:
        args = shlex.split(self.endpoint_or_command)
        if not args:
            raise ValueError("Empty stdio MCP command.")

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None
        request_line = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": uuid4().hex,
                    "method": method,
                    "params": params or {},
                }
            )
            + "\n"
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(request_line.encode("utf-8")),
                timeout=self._timeout,
            )
        finally:
            if proc.returncode is None:
                proc.kill()

        for line in stdout.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if "error" in parsed and parsed["error"] is not None:
                raise RuntimeError(f"MCP stdio error: {parsed['error']}")
            return parsed.get("result", {})
        return {}

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self.transport == "sse":
            return await self._rpc_sse(method, params)
        if self.transport == "stdio":
            return await self._rpc_stdio(method, params)
        raise ValueError(f"Unsupported MCP transport: {self.transport}")

    async def list_tools(self) -> list[DynamicToolSpec]:
        result = await self._rpc("tools/list")
        raw_tools = result.get("tools", []) if isinstance(result, dict) else []
        return [
            DynamicToolSpec(
                name=str(t["name"]),
                description=str(t.get("description", "")),
                parameters_schema=dict(t.get("inputSchema") or {"type": "object", "properties": {}}),
                source_kind="mcp",
                metadata={"transport": self.transport, "endpoint": self.endpoint_or_command},
            )
            for t in raw_tools
            if isinstance(t, dict) and t.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        return {"tool": name, "output": result}
