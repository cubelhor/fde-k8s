"""Native Google ADK Agents for the Kubernetes Troubleshooting Copilot.

Architecture:
- `planner_agent` (ADK Agent): Analyzes crash logs, queries K8s docs via Vertex AI Search (`search_kubernetes_documentation`), and writes `planner_checklist` to `session.state`.
- `executor_agent` (ADK Agent): Reads `{planner_checklist}` from `session.state` and generates structured `kubectl` commands using `output_schema=TroubleshootingPlan`, followed by deterministic `SafetyGuardian` validation in `after_agent_callback`.
- `root_orchestrator` (ADK SequentialAgent): Coordinates `planner_agent` -> `executor_agent` in a single ADK `Runner` execution.
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any

import yaml
from google.genai import types
from google.adk.agents import Agent, SequentialAgent, BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

import src.config  # noqa: F401 - initializes Vertex AI environment defaults
from src.models import IncidentState, TroubleshootingPlan
from src.guardrails import SafetyGuardian
from src.tools import search_kubernetes_documentation

APP_NAME = "k8s_troubleshooting_copilot"
DEFAULT_MODEL = "gemini-2.5-pro"
EXECUTOR_MODEL = "gemini-2.5-flash"
SCOPE_LOCK_PREFIX = "Error: Query is out of scope"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=6,
    initial_delay=4.0,
    max_delay=45.0,
    exp_base=2.0,
)


def load_prompt(filename: str) -> str:
    """Load a versioned system instruction prompt string from `backend/src/prompts/<filename>`."""
    with open(PROMPTS_DIR / filename, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["system_instruction"].strip()


# ============================================================================
# 1. Native ADK Lifecycle Callbacks (Checklist Normalization, Scope Lock & SafetyGuardian)
# ============================================================================

def planner_after_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    """Normalize `planner_checklist` into a list of step strings in `session.state`."""
    raw_checklist = callback_context.state.get("planner_checklist")
    if isinstance(raw_checklist, str):
        callback_context.state["planner_checklist"] = [
            line.strip() for line in raw_checklist.splitlines() if line.strip()
        ]
    callback_context.state["status"] = "PLANNING_COMPLETED"
    return None


def executor_before_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    """Short-circuit the Executor LLM call if `planner_agent` triggered the Scope Lock."""
    checklist = callback_context.state.get("planner_checklist") or []
    first_item = checklist[0] if isinstance(checklist, list) and checklist else str(checklist)
    if SCOPE_LOCK_PREFIX in first_item:
        out_of_scope_plan = TroubleshootingPlan(
            problem_summary=first_item,
            error_type="GeneralClusterAnomaly",
            steps=[],
            source_citations=["https://kubernetes.io/docs/home/"],
        )
        callback_context.state["troubleshooting_plan"] = out_of_scope_plan.model_dump()
        callback_context.state["status"] = "COMPLETED"
        return types.Content(
            role="model",
            parts=[types.Part.from_text(text=out_of_scope_plan.model_dump_json())],
        )
    return None


def executor_after_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    """Validate `TroubleshootingPlan` and run `SafetyGuardian` on every generated command."""
    raw_plan = callback_context.state.get("troubleshooting_plan")
    if raw_plan:
        plan = (
            TroubleshootingPlan.model_validate_json(raw_plan)
            if isinstance(raw_plan, str)
            else TroubleshootingPlan.model_validate(raw_plan)
        )

        # Run deterministic SafetyGuardian across all steps and merge grounded citations
        plan.steps = [SafetyGuardian.evaluate_command(cmd) for cmd in plan.steps]
        plan.source_citations = list(
            callback_context.state.get("source_citations")
            or plan.source_citations
            or [
                "https://kubernetes.io/docs/tasks/debug/",
                "https://kubernetes.io/docs/reference/kubectl/",
            ]
        )
        callback_context.state["source_citations"] = plan.source_citations
        callback_context.state["troubleshooting_plan"] = plan.model_dump()

    callback_context.state["status"] = "COMPLETED"
    return None


# ============================================================================
# 2. Native ADK Agent Definitions
# ============================================================================

planner_agent = Agent(
    model=Gemini(model=DEFAULT_MODEL, retry_options=RETRY_OPTIONS),
    name="planner_agent",
    description="Methodical Kubernetes SRE agent that analyzes crash logs and queries K8s reference docs.",
    instruction=load_prompt("planner_v1.yaml"),
    tools=[search_kubernetes_documentation],
    output_key="planner_checklist",
    after_agent_callback=planner_after_callback,
)

executor_agent = Agent(
    model=Gemini(model=EXECUTOR_MODEL, retry_options=RETRY_OPTIONS),
    name="executor_agent",
    description="Deterministic Kubernetes CLI Generator translating strategies into structured kubectl commands.",
    instruction=load_prompt("executor_v1.yaml"),
    output_schema=TroubleshootingPlan,
    output_key="troubleshooting_plan",
    before_agent_callback=executor_before_callback,
    after_agent_callback=executor_after_callback,
)

root_orchestrator = SequentialAgent(
    name="k8s_troubleshooting_orchestrator",
    description="Root Incident Commander for Kubernetes Troubleshooting coordinating planner_agent followed by executor_agent.",
    sub_agents=[planner_agent, executor_agent],
)

session_service = InMemorySessionService()
default_runner = Runner(
    agent=root_orchestrator,
    session_service=session_service,
    app_name=APP_NAME,
)
planner_runner = Runner(
    agent=planner_agent.clone(),
    session_service=session_service,
    app_name=APP_NAME,
)
_RUNNERS: Dict[str, Runner] = {
    root_orchestrator.name: default_runner,
    planner_agent.name: planner_runner,
}


# ============================================================================
# 3. Native ADK Runner Execution Helper
# ============================================================================

def _extract_usage_tokens(obj: Any) -> Dict[str, int]:
    """Extract integer token counts from an ADK Event usage_metadata."""
    usage = getattr(obj, "usage_metadata", None)
    if not usage:
        return {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}

    def _safe_int(val: Any) -> int:
        return int(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else 0

    return {
        "prompt_tokens": _safe_int(getattr(usage, "prompt_token_count", 0)),
        "cached_tokens": _safe_int(getattr(usage, "cached_content_token_count", 0)),
        "completion_tokens": _safe_int(getattr(usage, "candidates_token_count", 0)),
    }


async def run_agent_pipeline(
    state: IncidentState,
    agent: Optional[BaseAgent] = None,
) -> IncidentState:
    """Execute an ADK Agent or SequentialAgent (`root_orchestrator` or `planner_agent`) via ADK `Runner` and return hydrated `IncidentState`."""
    runner = _RUNNERS.get(agent.name, default_runner) if agent is not None else default_runner

    base_session_id = state.incident_id
    user_id = "sre-agent"
    initial_state = state.model_dump()

    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=state.raw_logs)],
    )

    prompt_tokens = 0
    cached_tokens = 0
    completion_tokens = 0
    t_start = time.perf_counter()
    t_planner_end = None
    t_executor_end = None
    updated_session = None

    for attempt in range(3):
        session_id = base_session_id if attempt == 0 else f"{base_session_id}-retry{attempt}"
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state=dict(initial_state),
        )
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                now = time.perf_counter()
                if event.author == "planner_agent":
                    t_planner_end = now
                elif event.author == "executor_agent":
                    t_executor_end = now

                tokens = _extract_usage_tokens(event)
                prompt_tokens += tokens["prompt_tokens"]
                cached_tokens += tokens["cached_tokens"]
                completion_tokens += tokens["completion_tokens"]

            updated_session = await session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            if updated_session and updated_session.state.get("planner_checklist"):
                break
        except ValueError as err:
            if attempt == 2:
                raise err

    session_state_dict = dict(updated_session.state) if updated_session else initial_state

    meta = dict(session_state_dict.get("metadata") or {})
    if t_planner_end is not None:
        meta["planner_latency_ms"] = round((t_planner_end - t_start) * 1000.0, 2)
    if t_executor_end is not None:
        exec_start = t_planner_end if t_planner_end is not None else t_start
        meta["executor_latency_ms"] = round((t_executor_end - exec_start) * 1000.0, 2)
    if prompt_tokens > 0 or completion_tokens > 0:
        meta["prompt_tokens"] = meta.get("prompt_tokens", 0) + prompt_tokens
        meta["cached_tokens"] = meta.get("cached_tokens", 0) + cached_tokens
        meta["completion_tokens"] = meta.get("completion_tokens", 0) + completion_tokens
    session_state_dict["metadata"] = meta

    return IncidentState.model_validate(session_state_dict)
