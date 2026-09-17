"""Tests for YAML Prompt Externalization (`load_prompt`) and AI Safety Scope Locking."""

import os
import sys
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.models import IncidentState
from src.agents import (
    load_prompt,
    create_planner_agent,
    create_executor_agent,
    PlannerAgent,
    SCOPE_LOCK_MESSAGE,
)


def test_load_prompt_reads_planner_and_executor_yaml_files():
    """Verify load_prompt reads both planner_v1.yaml and executor_v1.yaml and injects them into ADK agents."""
    planner_prompt = load_prompt("planner_v1.yaml")
    executor_prompt = load_prompt("executor_v1.yaml")

    assert isinstance(planner_prompt, str) and len(planner_prompt) > 100
    assert isinstance(executor_prompt, str) and len(executor_prompt) > 100

    # Verify Scope Lock rule is present in planner_v1.yaml
    assert "Error: Query is out of scope. Please provide a Kubernetes-related issue." in planner_prompt
    assert "search_kubernetes_documentation" in planner_prompt
    assert "TroubleshootingPlan" in executor_prompt

    # Verify create_planner_agent and create_executor_agent dynamically inject the YAML instructions
    planner_adk = create_planner_agent()
    executor_adk = create_executor_agent()
    assert planner_adk.instruction == planner_prompt
    assert executor_adk.instruction == executor_prompt


@pytest.mark.asyncio
async def test_planner_agent_scope_lock_refuses_off_topic_query():
    """Verify PlannerAgent refuses non-Kubernetes queries with the Scope Lock refusal message."""
    planner = PlannerAgent()
    state = IncidentState(
        incident_id="inc-scope-lock-test",
        raw_logs="Write a recipe for chocolate cake",
    )

    updated_state = await planner.plan(state)

    assert updated_state.status == "PLANNING_COMPLETED"
    assert updated_state.planner_checklist == [
        "Error: Query is out of scope. Please provide a Kubernetes-related issue."
    ]
    assert updated_state.planner_checklist[0] == SCOPE_LOCK_MESSAGE
    assert updated_state.retrieved_docs == []
