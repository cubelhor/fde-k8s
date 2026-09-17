"""Automated async test suite for RootOrchestrator delegation and status_history transitions."""

import os
import sys
from unittest.mock import MagicMock, AsyncMock
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from google.adk.agents import SequentialAgent
from src.agents import RootOrchestrator, PlannerAgent, ExecutorAgent
from src.models import IncidentState


@pytest.mark.asyncio
async def test_root_orchestrator_delegation_and_status_history():
    """Verify RootOrchestrator delegates to PlannerAgent and ExecutorAgent in order and records status_history."""
    state = IncidentState(raw_logs="Test crash")

    mock_planner = MagicMock(spec=PlannerAgent)
    mock_executor = MagicMock(spec=ExecutorAgent)

    async def mock_plan(s: IncidentState) -> IncidentState:
        s.metadata.setdefault("status_history", []).append("PLANNING_COMPLETED")
        s.status = "PLANNING_COMPLETED"
        return s

    async def mock_execute(s: IncidentState) -> IncidentState:
        s.metadata.setdefault("status_history", []).append("EXECUTED")
        s.status = "EXECUTED"
        return s

    mock_planner.plan = AsyncMock(side_effect=mock_plan)
    mock_executor.execute = AsyncMock(side_effect=mock_execute)

    orchestrator = RootOrchestrator(planner=mock_planner, executor=mock_executor)
    assert isinstance(orchestrator.adk_agent, SequentialAgent)

    state = await orchestrator.orchestrate(state)

    assert state.status == "COMPLETED"
    assert state.metadata["status_history"] == [
        "PLANNING_COMPLETED",
        "EXECUTED",
        "COMPLETED",
    ]
    mock_planner.plan.assert_awaited_once()
    mock_executor.execute.assert_awaited_once()
    assert mock_planner.plan.call_count == 1
    assert mock_executor.execute.call_count == 1
