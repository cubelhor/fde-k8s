"""Unit tests for RootOrchestrator multi-agent delegation and state transitions."""

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
from src.models import IncidentState, KubectlCommand


@pytest.mark.asyncio
async def test_root_orchestrator_delegation_order_and_status_transitions():
    """Verify RootOrchestrator (SequentialAgent) calls PlannerAgent then ExecutorAgent in order and transitions status to COMPLETED."""
    call_order = []

    mock_planner = MagicMock(spec=PlannerAgent)
    mock_executor = MagicMock(spec=ExecutorAgent)

    async def fake_plan(state: IncidentState) -> IncidentState:
        call_order.append("planner")
        assert state.status == "INITIALIZED"
        state.planner_checklist = [
            "1. Inspect pod CrashLoopBackOff events with kubectl describe pod.",
            "2. Check container exit code and previous logs.",
        ]
        state.source_citations = [
            "Pods > Pod Lifecycle (https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)"
        ]
        state.status = "PLANNING_COMPLETED"
        return state

    async def fake_execute(state: IncidentState) -> IncidentState:
        call_order.append("executor")
        # Verify planner ran before executor and updated status to PLANNING_COMPLETED
        assert state.status == "PLANNING_COMPLETED"
        assert len(state.planner_checklist) == 2
        cmd = KubectlCommand(
            step_number=1,
            title="Describe Failing Pod",
            command="kubectl describe pod auth-api-7f8d9b -n prod",
            explanation="Check pod events and last termination state.",
            danger_level="LOW",
            alternative_command=None,
        )
        state.raw_command = [cmd]
        state.final_validated_command = [cmd]
        state.status = "EXECUTED"
        return state

    mock_planner.plan = AsyncMock(side_effect=fake_plan)
    mock_executor.execute = AsyncMock(side_effect=fake_execute)

    orchestrator = RootOrchestrator(planner=mock_planner, executor=mock_executor)
    assert isinstance(orchestrator.adk_agent, SequentialAgent)
    assert [sub.name for sub in orchestrator.adk_agent.sub_agents] == ["planner_agent", "executor_agent"]

    initial_state = IncidentState(
        incident_id="inc-orch-001",
        raw_logs="Back-off restarting failed container auth-api in pod auth-api-7f8d9b_prod",
        cluster_context="prod",
        status="INITIALIZED",
    )

    final_state = await orchestrator.orchestrate(initial_state)

    # Verify both subagents were called once in strict sequence
    mock_planner.plan.assert_awaited_once()
    mock_executor.execute.assert_awaited_once()
    assert call_order == ["planner", "executor"]

    # Verify state status transitions ("PLANNING_COMPLETED" -> "EXECUTED" -> "COMPLETED")
    assert final_state.metadata.get("status_history") == [
        "PLANNING_COMPLETED",
        "EXECUTED",
        "COMPLETED",
    ]
    assert final_state.status == "COMPLETED"
    assert len(final_state.planner_checklist) == 2
    assert len(final_state.final_validated_command) == 1
    assert final_state.final_validated_command[0].command == "kubectl describe pod auth-api-7f8d9b -n prod"
