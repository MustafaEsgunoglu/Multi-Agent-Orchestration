"""API v1 master router."""

from fastapi import APIRouter

from app.api.v1 import api_keys, auth, copilot, executions, mcp, rag, workflows

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(api_keys.router)
api_v1_router.include_router(workflows.router)
api_v1_router.include_router(executions.router)
api_v1_router.include_router(rag.router)
api_v1_router.include_router(mcp.router)
api_v1_router.include_router(copilot.router)
