"""Tests for FastAPI endpoints, RLS SQL generation, and auth guards."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import RLS_PROTECTED_TABLES
from app.db.rls import build_rls_enable_sql
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_workflow_schema_and_validation_endpoints() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        schema_resp = await client.get("/api/v1/workflows/schema")
        assert schema_resp.status_code == 200
        schema_json = schema_resp.json()
        assert "properties" in schema_json
        assert "nodes" in schema_json["properties"]

        valid_payload = {
            "schema_version": "1.0",
            "nodes": [
                {"id": "s", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
                {"id": "e", "type": "end", "position": {"x": 100, "y": 0}, "data": {"label": "End"}},
            ],
            "edges": [{"id": "e1", "source": "s", "target": "e"}],
        }
        val_resp = await client.post("/api/v1/workflows/validate", json=valid_payload)
        assert val_resp.status_code == 200
        assert val_resp.json()["valid"] is True
        assert val_resp.json()["recursion_limit"] == 25


@pytest.mark.asyncio
async def test_protected_endpoints_reject_unauthenticated_requests() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api/v1/workflows", "/api/v1/api-keys", "/api/v1/auth/me"):
            resp = await client.get(path)
            assert resp.status_code == 401


def test_rls_sql_generation_covers_all_tenant_tables() -> None:
    assert "workflows" in RLS_PROTECTED_TABLES
    assert "api_keys" in RLS_PROTECTED_TABLES
    assert "document_chunks" in RLS_PROTECTED_TABLES
    for table in RLS_PROTECTED_TABLES:
        enable_sql, force_sql, policy_sql = build_rls_enable_sql(table)
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;' == enable_sql
        assert f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;' == force_sql
        assert "app.current_tenant_id" in policy_sql
