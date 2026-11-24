"""Shared LangGraph StateGraph state schema and execution exceptions."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ExecutionError(RuntimeError):
    """Base error for workflow compilation or runtime failures."""


class CostLimitExceededError(ExecutionError):
    """Raised when accumulated USD cost reaches execution_config.max_cost_usd."""


class WorkflowState(TypedDict, total=False):
    """Canonical mutable state flowing through every compiled LangGraph StateGraph."""

    input: dict[str, Any]
    messages: Annotated[list[dict[str, Any]], operator.add]
    context: dict[str, Any]
    last_output: str
    next_route: str | None
    step_metrics: Annotated[list[dict[str, Any]], operator.add]
    total_tokens: int
    total_cost_usd: float
    human_decision: str | None
    final_output: dict[str, Any]
