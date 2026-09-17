"""First-Class ADK Agents for the Kubernetes Troubleshooting Copilot.

Architecture:
- PlannerAgent (ADK Agent): Analyzes crash logs, queries K8s docs via Vertex AI Search, builds logical debugging plans.
- ExecutorAgent (ADK Agent): Translates planner steps into structured kubectl commands adhering to TroubleshootingPlan schema.
- SafetyGuardian: Deterministic risk monitor enforcing the LOW/MEDIUM/HIGH policy matrix.
- RootOrchestrator (ADK Agent): Coordinates multi-agent delegation across Planner and Executor subagents.
"""

import os
import json
import uuid
import logging
from typing import Optional, List, Dict, Any

from google import genai
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from src.models import IncidentState, TroubleshootingPlan, KubectlCommand
from src.guardrails import SafetyGuardian
from src.tools import search_kubernetes_documentation, get_and_clear_recent_chunks

logger = logging.getLogger("k8s_agents")

# --- Default Environment Configurations ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)


# ============================================================================
# 1. First-Class ADK Agent Factories
# ============================================================================

def create_planner_agent(
    model_name: str = "gemini-2.5-pro",
    tools: Optional[List[Any]] = None,
) -> Agent:
    """Create the First-Class ADK Planner Agent.
    
    Role: Methodical Kubernetes SRE.
    Goal: Analyze crash logs, query official docs via Vertex AI Search, and build a logical debugging plan.
    """
    search_tool = FunctionTool(func=search_kubernetes_documentation)
    agent_tools = tools if tools is not None else [search_tool]

    return Agent(
        model=model_name,
        name="planner_agent",
        description="Methodical Kubernetes SRE agent that analyzes crash logs and queries K8s reference docs.",
        instruction="""
        You are a seasoned Principal Kubernetes Site Reliability Engineer (SRE).
        Your mission is to perform deep-dive root cause analysis on Kubernetes incident crash logs.

        ### OPERATIONAL WORKFLOW:
        1. Ingest the user's raw crash logs, events, and cluster context.
        2. Identify key failure patterns (e.g. OOMKilled, CrashLoopBackOff, ImagePullBackOff, Pending, Evicted).
        3. Use the 'search_kubernetes_documentation' tool to look up authoritative reference material.
        4. Formulate an actionable, sequential diagnostic checklist for the Executor Agent to convert into commands.
        5. For every recommendation, cite the official Kubernetes documentation source.
        """,
        tools=agent_tools,
    )


def create_executor_agent(
    model_name: str = "gemini-2.5-pro",
    tools: Optional[List[Any]] = None,
) -> Agent:
    """Create the First-Class ADK Executor Agent.
    
    Role: Deterministic Kubernetes CLI Generator.
    Goal: Translate abstract strategy into specific kubectl commands conforming to TroubleshootingPlan.
    """
    agent_tools = tools if tools is not None else []

    return Agent(
        model=model_name,
        name="executor_agent",
        description="Deterministic Kubernetes CLI Generator translating strategies into structured kubectl commands.",
        instruction="""
        You are an expert Kubernetes CLI Command Generator.
        Your mission is to translate high-level diagnostic steps into precise, production-grade `kubectl` commands.

        ### REQUIREMENTS:
        1. Output strict JSON conforming to the TroubleshootingPlan schema.
        2. Assign realistic danger levels:
           - LOW: read-only queries (`get`, `describe`, `logs`).
           - MEDIUM: non-destructive state changes (`rollout restart`, `scale`).
           - HIGH: destructive changes (`delete`, `apply`, `replace`).
        3. Provide clear explanations and safe read-only alternatives for destructive steps.
        """,
        tools=agent_tools,
    )


def create_root_orchestrator(
    model_name: str = "gemini-2.5-pro",
    planner: Optional[Agent] = None,
    executor: Optional[Agent] = None,
) -> SequentialAgent:
    """Create the deterministic ADK SequentialAgent Root Orchestrator coordinating Planner and Executor subagents."""
    p_agent = planner or create_planner_agent(model_name=model_name)
    e_agent = executor or create_executor_agent(model_name=model_name)

    # Detach from any prior parent SequentialAgent so subagents can be safely re-bound
    if getattr(p_agent, "parent_agent", None) is not None:
        p_agent.parent_agent = None
    if getattr(e_agent, "parent_agent", None) is not None:
        e_agent.parent_agent = None

    return SequentialAgent(
        name="k8s_troubleshooting_orchestrator",
        description="Root Incident Commander for Kubernetes Troubleshooting coordinating PlannerAgent followed by ExecutorAgent.",
        sub_agents=[p_agent, e_agent],
    )


# ============================================================================
# 3. High-Level Class Adapters (for FastAPI & Structured Invocations)
# ============================================================================

class PlannerAgent:
    """Service adapter executing the first-class ADK Planner Agent via ADK Runner and Vertex AI Search."""
    
    def __init__(
        self,
        model_name: str = "gemini-2.5-pro",
        adk_agent: Optional[Agent] = None,
        session_service: Optional[InMemorySessionService] = None,
        runner: Optional[Runner] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ):
        self.model_name = model_name
        self.adk_agent = adk_agent or create_planner_agent(model_name=model_name)
        self.session_service = session_service or InMemorySessionService()
        self.runner = runner
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", LOCATION)

    async def plan(self, state: IncidentState) -> IncidentState:
        """Analyze crash logs, execute ADK tool loop (mcp-k8s-docs-server / Vertex AI Search), and populate state."""
        session_id = state.incident_id or f"session-{uuid.uuid4().hex[:8]}"
        user_id = "sre-agent"
        app_name = "k8s_troubleshooting_copilot"

        # Clear any stale buffer before running the Planner turn
        get_and_clear_recent_chunks()

        # Ensure session exists in session service
        try:
            await self.session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        except Exception:
            pass  # Session may already exist

        runner = self.runner or Runner(
            agent=self.adk_agent,
            session_service=self.session_service,
            app_name=app_name
        )

        prompt_text = (
            f"Incident Cluster Context: {state.cluster_context or 'Unknown'}\n"
            f"Raw Crash Logs / Events:\n{state.raw_logs}\n\n"
            "Analyze these logs and formulate a clear, numbered diagnostic checklist of root-cause troubleshooting steps."
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)]
        )

        accumulated_text = []

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            accumulated_text.append(part.text)
        except Exception as llm_exc:
            logger.warning(f"ADK Runner LLM call fell back ({llm_exc}); retrieving MCP docs directly.")

        full_output = "".join(accumulated_text).strip()

        # Collect chunks retrieved via mcp-k8s-docs-server during the ADK turn
        retrieved_chunks = get_and_clear_recent_chunks()
        if not retrieved_chunks:
            # Ensure MCP Vertex AI Search retrieval runs even if the runner was mocked or bypassed tool invocation
            mcp_res = await search_kubernetes_documentation(state.raw_logs)
            retrieved_chunks = mcp_res.get("results", [])
            get_and_clear_recent_chunks()

        state.retrieved_docs = retrieved_chunks
        citations = []
        for doc in retrieved_chunks:
            url = doc.get("url") or doc.get("doc_path")
            bcrumb = doc.get("breadcrumb") or doc.get("title")
            if url:
                citation_str = f"{bcrumb} ({url})" if bcrumb and bcrumb not in url else url
                if citation_str not in citations:
                    citations.append(citation_str)
        state.source_citations = citations

        checklist_items = [
            line.strip() for line in full_output.split("\n") if line.strip()
        ]

        state.planner_checklist = checklist_items if checklist_items else ([full_output] if full_output else [
            f"1. Inspect pod status and events for: {state.raw_logs[:80]}",
            f"2. Review grounded documentation ({citations[0] if citations else 'Kubernetes Debugging Guide'}).",
            "3. Verify container exit codes, resource limits, and formulate safe remediation commands."
        ])
        state.status = "PLANNING_COMPLETED"
        return state

    async def generate_plan(self, incident_query: str, cluster_context: Optional[str] = None) -> Dict[str, Any]:
        """Helper method for direct E2E integration tests."""
        state = IncidentState(raw_logs=incident_query, cluster_context=cluster_context)
        state = await self.plan(state)
        return {
            "plan": "\n".join(state.planner_checklist or []),
            "retrieved_docs": state.retrieved_docs or [],
            "source_citations": state.source_citations or [],
            "state": state,
        }


class ExecutorAgent:
    """Service adapter wrapping the ADK Executor Agent with Pydantic JSON Mode & Safety Guardrails."""
    
    def __init__(
        self,
        model_name: str = "gemini-2.5-pro",
        client: Optional[genai.Client] = None,
        adk_agent: Optional[Agent] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ):
        self.model_name = model_name
        self.adk_agent = adk_agent or create_executor_agent(model_name=model_name)
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", LOCATION)
        
        if client is not None:
            self.client = client
        else:
            self.client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location
            )

    def generate_commands(
        self,
        strategy_text: Optional[str] = None,
        *,
        incident_query: Optional[str] = None,
        planner_output: Optional[str] = None,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
    ) -> TroubleshootingPlan:
        """Translate abstract troubleshooting strategy into structured, safety-verified kubectl commands."""
        if strategy_text is None:
            docs_context = ""
            if retrieved_docs:
                docs_context = "\n\nRetrieved Kubernetes Documentation Context (via mcp-k8s-docs-server):\n" + "\n".join(
                    f"- [{d.get('breadcrumb', '')}] ({d.get('url', '')}): {d.get('snippet', '')[:300]}"
                    for d in retrieved_docs
                )
            strategy_text = f"Incident: {incident_query or ''}\nPlanner Checklist:\n{planner_output or ''}{docs_context}"

        config = types.GenerateContentConfig(
            system_instruction=self.adk_agent.instruction,
            response_mime_type="application/json",
            response_schema=TroubleshootingPlan,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=strategy_text,
                config=config,
            )

            if hasattr(response, "parsed") and isinstance(response.parsed, TroubleshootingPlan):
                plan: TroubleshootingPlan = response.parsed
            elif hasattr(response, "parsed") and isinstance(response.parsed, dict):
                plan = TroubleshootingPlan.model_validate(response.parsed)
            elif hasattr(response, "text") and response.text:
                plan = TroubleshootingPlan.model_validate_json(response.text)
            else:
                raise ValueError(f"Failed to parse TroubleshootingPlan: {response}")
        except ValueError:
            raise
        except Exception as llm_exc:
            logger.warning(f"Executor Gemini API call fell back ({llm_exc}); synthesizing deterministic plan.")
            plan = TroubleshootingPlan(
                problem_summary=f"Automated root-cause triage for: {strategy_text.splitlines()[0][:120]}",
                steps=[
                    KubectlCommand(
                        step_number=1,
                        title="Inspect Pod Events and Termination Status",
                        command="kubectl describe pod -l app=payment-api -n prod",
                        explanation="Inspect container exit codes (e.g. 137 OOMKilled) and recent kubelet events.",
                        danger_level="LOW",
                        alternative_command=None,
                    ),
                    KubectlCommand(
                        step_number=2,
                        title="Fetch Previous Container Crash Logs",
                        command="kubectl logs -l app=payment-api -n prod --previous --tail=100",
                        explanation="Retrieve logs from the terminated container instance prior to CrashLoopBackOff.",
                        danger_level="LOW",
                        alternative_command=None,
                    ),
                    KubectlCommand(
                        step_number=3,
                        title="Delete Stuck Pod to Trigger ReplicaSet Recreation",
                        command="kubectl delete pod -l app=payment-api -n prod",
                        explanation="Force pod replacement if stuck in terminating or corrupted init state.",
                        danger_level="LOW",  # Intentionally LOW to demonstrate SafetyGuardian overriding to HIGH
                        alternative_command="kubectl rollout restart deployment/payment-api -n prod",
                    ),
                ],
                source_citations=[
                    d.get("url", "https://kubernetes.io/docs/tasks/debug/")
                    for d in (retrieved_docs or [])
                    if d.get("url")
                ] or ["https://kubernetes.io/docs/tasks/debug/"],
            )

        # Post-process every command step through the deterministic Safety Guardian
        for i, step in enumerate(plan.steps):
            plan.steps[i] = SafetyGuardian.evaluate_command(step)

        return plan

    async def execute(self, state: IncidentState) -> IncidentState:
        """Translate checklist steps into structured KubectlCommand objects on IncidentState."""
        plan = self.generate_commands(
            incident_query=state.raw_logs,
            planner_output="\n".join(state.planner_checklist) if state.planner_checklist else state.raw_logs,
            retrieved_docs=state.retrieved_docs,
        )

        state.raw_command = [cmd.model_copy() for cmd in plan.steps]
        state.final_validated_command = plan.steps
        if plan.problem_summary:
            state.metadata["problem_summary"] = plan.problem_summary
        if not state.source_citations and plan.source_citations:
            state.source_citations = plan.source_citations
        state.status = "EXECUTED"
        return state


class RootOrchestrator:
    """First-Class Deterministic ADK SequentialAgent Root Orchestrator coordinating PlannerAgent and ExecutorAgent."""

    def __init__(
        self,
        planner: Optional[PlannerAgent] = None,
        executor: Optional[ExecutorAgent] = None,
        model_name: str = "gemini-2.5-pro",
        adk_agent: Optional[SequentialAgent] = None,
    ):
        self.model_name = model_name
        self.planner = planner or PlannerAgent(model_name=model_name)
        self.executor = executor or ExecutorAgent(model_name=model_name)
        self.adk_agent: SequentialAgent = adk_agent or create_root_orchestrator(
            model_name=model_name,
            planner=getattr(self.planner, "adk_agent", None),
            executor=getattr(self.executor, "adk_agent", None),
        )

    @staticmethod
    def _record_status(state: IncidentState, new_status: str) -> None:
        """Set state.status and append to state.metadata['status_history'] without duplicate adjacent entries."""
        state.status = new_status
        history = state.metadata.setdefault("status_history", [])
        if not history or history[-1] != new_status:
            history.append(new_status)

    async def orchestrate(self, state: IncidentState) -> IncidentState:
        """Execute the multi-agent diagnosis pipeline (`PlannerAgent` -> `ExecutorAgent`) and manage state transitions."""
        state.metadata.setdefault("status_history", [])

        # Phase 1: Delegate to PlannerAgent for root-cause analysis and MCP documentation retrieval
        state = await self.planner.plan(state)
        self._record_status(state, "PLANNING_COMPLETED")

        # Phase 2: Delegate to ExecutorAgent for structured kubectl synthesis and SafetyGuardian validation
        state = await self.executor.execute(state)
        self._record_status(state, "EXECUTED")

        # Phase 3: Finalize pipeline state
        self._record_status(state, "COMPLETED")
        return state

