"""Tests for Phase 3: PyMuPDF RAG, OpenAPI/MCP tool loader, AI Copilot, and Celery tasks."""

from __future__ import annotations

import json

import httpx
import pymupdf
import pytest

from app.engine.copilot import generate_workflow_from_prompt
from app.engine.llm import LLMCallResult
from app.engine.mcp_client import MCPClient, invoke_openapi_tool, parse_openapi_spec
from app.main import app as fastapi_app
from app.rag.chunker import chunk_text
from app.rag.parser import parse_document_bytes
from app.workers import tasks as _worker_tasks  # noqa: F401
from app.workers.celery_app import celery_app


class SequencedFakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def acomplete(
        self,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMCallResult:
        content = self._responses.pop(0)
        return LLMCallResult(
            content=content,
            model=f"{provider}/{model}",
            prompt_tokens=200,
            completion_tokens=150,
            total_tokens=350,
            estimated_cost_usd=0.001,
        )


def test_pymupdf_pdf_extraction_and_recursive_chunking() -> None:
    # Build an in-memory PDF with PyMuPDF
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 780),
        "Multi-Agent Orchestration Architecture.\n\n"
        + ("PostgreSQL pgvector enables low-RAM RAG without extra vector databases. " * 25),
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()

    parsed = parse_document_bytes(pdf_bytes, filename="architecture.pdf")
    assert parsed.page_count == 1
    assert "Multi-Agent Orchestration Architecture." in parsed.text

    chunks = chunk_text(parsed.text, chunk_size=300, chunk_overlap=50)
    assert len(chunks) >= 3
    assert all(c.content.strip() for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.asyncio
async def test_openapi_spec_conversion_and_invocation() -> None:
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/tickets/{ticket_id}": {
                "get": {
                    "operationId": "getTicket",
                    "summary": "Fetch support ticket by ID",
                    "parameters": [
                        {"name": "ticket_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "include_logs", "in": "query", "required": False, "schema": {"type": "boolean"}},
                    ],
                }
            }
        },
    }

    tools = parse_openapi_spec(spec)
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "getTicket"
    assert "ticket_id" in tool.parameters_schema["required"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.example.com/tickets/TK-42?include_logs=true"
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"id": "TK-42", "status": "open"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await invoke_openapi_tool(
            tool,
            {"ticket_id": "TK-42", "include_logs": "true"},
            auth_headers={"Authorization": "Bearer secret-token"},
            http_client=client,
        )
    assert res["ok"] is True
    assert res["output"]["status"] == "open"


@pytest.mark.asyncio
async def test_mcp_sse_client_lists_and_calls_tools() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert request.headers["X-API-Key"] == "mcp-secret"
        if body["method"] == "tools/list":
            sse_payload = (
                "event: message\n"
                'data: {"jsonrpc":"2.0","id":"1","result":{"tools":[{"name":"search_crm","description":"Search CRM","inputSchema":{"type":"object","properties":{"q":{"type":"string"}}}}]}}\n\n'
            )
            return httpx.Response(
                200,
                content=sse_payload,
                headers={"content-type": "text/event-stream"},
            )
        if body["method"] == "tools/call":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": "2", "result": {"matches": ["Acme Corp"]}},
            )
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        mcp = MCPClient(
            transport="sse",
            endpoint_or_command="https://mcp.example.com/sse",
            auth_headers={"X-API-Key": "mcp-secret"},
            http_client=client,
        )
        tools = await mcp.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "search_crm"

        call_res = await mcp.call_tool("search_crm", {"q": "Acme"})
        assert call_res["output"]["matches"] == ["Acme Corp"]


@pytest.mark.asyncio
async def test_copilot_self_heals_invalid_first_attempt() -> None:
    # First attempt has recursion_limit=99 (violates <=50 guardrail); second attempt fixes it.
    bad_json = json.dumps(
        {
            "explanation": "Draft with bad limit",
            "workflow": {
                "schema_version": "1.0",
                "execution_config": {"recursion_limit": 99},
                "nodes": [
                    {"id": "s", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
                    {"id": "e", "type": "end", "position": {"x": 240, "y": 0}, "data": {"label": "End"}},
                ],
                "edges": [{"id": "e1", "source": "s", "target": "e"}],
            },
        }
    )
    good_json = json.dumps(
        {
            "explanation": "Fixed research workflow",
            "workflow": {
                "schema_version": "1.0",
                "execution_config": {"recursion_limit": 25},
                "nodes": [
                    {"id": "s", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
                    {"id": "researcher", "type": "agent", "position": {"x": 240, "y": 0}, "data": {"label": "Researcher"}},
                    {"id": "e", "type": "end", "position": {"x": 480, "y": 0}, "data": {"label": "End"}},
                ],
                "edges": [
                    {"id": "e1", "source": "s", "target": "researcher"},
                    {"id": "e2", "source": "researcher", "target": "e"},
                ],
            },
        }
    )

    result = await generate_workflow_from_prompt(
        "Create a research agent workflow",
        llm_client=SequencedFakeLLM([bad_json, f"```json\n{good_json}\n```"]),
    )
    assert result.attempts == 2
    assert result.workflow.execution_config.recursion_limit == 25
    assert len(result.workflow.nodes) == 3
    assert result.total_tokens == 700


@pytest.mark.asyncio
async def test_openapi_preview_endpoint_and_celery_registration() -> None:
    assert "orchestrator.ingest_document" in celery_app.tasks
    assert "orchestrator.execute_workflow_async" in celery_app.tasks

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/integrations/openapi/preview-tools",
            json={
                "spec": {
                    "openapi": "3.0.0",
                    "paths": {"/ping": {"get": {"operationId": "pingHealth"}}},
                }
            },
        )
    assert resp.status_code == 200
    assert resp.json()["tool_count"] == 1
    assert resp.json()["tools"][0]["name"] == "pingHealth"
