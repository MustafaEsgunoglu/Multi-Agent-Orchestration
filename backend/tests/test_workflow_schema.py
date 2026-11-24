"""Tests for canonical WorkflowDefinition schema & execution guardrails."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.workflow import WorkflowDefinition


def _sample_multi_agent_workflow() -> dict:
    return {
        "schema_version": "1.0",
        "execution_config": {"recursion_limit": 25, "timeout_seconds": 180},
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "position": {"x": 0, "y": 100},
                "data": {"label": "Start"},
            },
            {
                "id": "sup_1",
                "type": "supervisor",
                "position": {"x": 240, "y": 100},
                "data": {
                    "label": "Lead Supervisor",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "managed_agent_ids": ["agent_research"],
                },
            },
            {
                "id": "agent_research",
                "type": "agent",
                "position": {"x": 480, "y": 100},
                "data": {
                    "label": "Research Agent",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "rag_enabled": True,
                    "rag_top_k": 5,
                },
            },
            {
                "id": "hitl_1",
                "type": "human_approval",
                "position": {"x": 720, "y": 100},
                "data": {"label": "Manager Approval"},
            },
            {
                "id": "end_1",
                "type": "end",
                "position": {"x": 960, "y": 100},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "sup_1"},
            {"id": "e2", "source": "sup_1", "target": "agent_research"},
            {"id": "e3", "source": "agent_research", "target": "hitl_1"},
            {"id": "e4", "source": "hitl_1", "target": "end_1", "condition": "approve"},
        ],
    }


def test_valid_multi_agent_workflow_parses() -> None:
    wf = WorkflowDefinition.model_validate(_sample_multi_agent_workflow())
    assert wf.execution_config.recursion_limit == 25
    assert len(wf.nodes) == 5
    assert len(wf.edges) == 4


def test_recursion_limit_above_50_is_rejected() -> None:
    raw = _sample_multi_agent_workflow()
    raw["execution_config"]["recursion_limit"] = 51
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate(raw)


def test_dangling_edge_target_is_rejected() -> None:
    raw = _sample_multi_agent_workflow()
    raw["edges"].append({"id": "e_bad", "source": "sup_1", "target": "non_existent"})
    with pytest.raises(ValidationError, match="unknown target node"):
        WorkflowDefinition.model_validate(raw)


def test_duplicate_node_ids_are_rejected() -> None:
    raw = _sample_multi_agent_workflow()
    raw["nodes"].append(raw["nodes"][-1])
    with pytest.raises(ValidationError, match="Duplicate node id"):
        WorkflowDefinition.model_validate(raw)


def test_missing_start_node_is_rejected() -> None:
    raw = _sample_multi_agent_workflow()
    raw["nodes"] = [n for n in raw["nodes"] if n["type"] != "start"]
    raw["edges"] = [e for e in raw["edges"] if e["source"] != "start_1"]
    with pytest.raises(ValidationError, match="exactly one 'start' node"):
        WorkflowDefinition.model_validate(raw)


def test_self_loop_is_rejected() -> None:
    raw = _sample_multi_agent_workflow()
    raw["edges"].append({"id": "e_loop", "source": "agent_research", "target": "agent_research"})
    with pytest.raises(ValidationError, match="self-loop"):
        WorkflowDefinition.model_validate(raw)
