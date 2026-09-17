"""Unit tests for First-Class ADK Agent configurations and tools."""

import os
import sys
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from google.adk.agents import Agent, SequentialAgent
from src.agents import (
    create_planner_agent,
    create_executor_agent,
    create_root_orchestrator,
    search_kubernetes_documentation,
)
from src.models import IncidentState


def test_planner_adk_agent_configuration():
    """Verify that PlannerAgent is a valid first-class ADK Agent with tools and instructions."""
    planner = create_planner_agent(model_name="gemini-2.5-pro")

    assert isinstance(planner, Agent)
    assert planner.name == "planner_agent"
    assert planner.model == "gemini-2.5-pro"
    assert "Kubernetes Site Reliability Engineer" in planner.instruction
    assert len(planner.tools) >= 1
    
    # Check that search tool is attached
    tool_names = [getattr(t, "name", str(t)) for t in planner.tools]
    assert any("search_kubernetes_documentation" in name for name in tool_names)


def test_executor_adk_agent_configuration():
    """Verify that ExecutorAgent is a valid first-class ADK Agent with NO tools (strictly Gemini Structured Outputs)."""
    executor = create_executor_agent(model_name="gemini-2.5-pro")

    assert isinstance(executor, Agent)
    assert executor.name == "executor_agent"
    assert executor.model == "gemini-2.5-pro"
    assert "Kubernetes CLI Command Generator" in executor.instruction
    assert len(executor.tools) == 0


def test_root_orchestrator_configuration():
    """Verify that Root Orchestrator is a deterministic ADK SequentialAgent with Planner and Executor subagents."""
    orchestrator = create_root_orchestrator(model_name="gemini-2.5-pro")

    assert isinstance(orchestrator, SequentialAgent)
    assert orchestrator.name == "k8s_troubleshooting_orchestrator"
    assert "Root Incident Commander" in orchestrator.description
    assert len(orchestrator.sub_agents) == 2
    assert [sub.name for sub in orchestrator.sub_agents] == ["planner_agent", "executor_agent"]


@pytest.mark.asyncio
async def test_adk_search_tool_fallback():
    """Test the ADK search_kubernetes_documentation fallback when offline."""
    res = await search_kubernetes_documentation("CrashLoopBackOff")
    assert "results" in res
    assert len(res["results"]) > 0
    assert "CrashLoopBackOff" in res["query"]
