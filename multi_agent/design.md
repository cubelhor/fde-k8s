# Project: Kubernetes Troubleshooting Copilot

## 1. System Overview
We are building a high-performance, context-grounded agentic platform to assist SREs in debugging K8s anomalies. It uses a decoupled Planner-Executor architecture, enforces strict schema compliance via Pydantic, and features a determinist safety guardrail.

**State Management:** Use a Pydantic `IncidentState` class to pass data between the agents tracking `raw_logs`, `planner_checklist`, `source_citations`, and `troubleshooting_plan`.

## 2. Tech Stack & Infrastructure
- **Framework:** Google ADK (`Agent` + `SequentialAgent` + `InMemorySessionService` + `Runner`)
- **Runtime:** FastAPI (Cloud Run)
- **Language:** Python 3.11+
- **LLM:** Gemini 2.5 Pro (`gemini-2.5-pro`)
- **Validation:** Pydantic (Strict Schema Enforcement via `output_schema=TroubleshootingPlan`)
- **Observability:** OpenTelemetry (OTEL) traces to Cloud Trace; token metrics to BigQuery; user feedback to Firestore.

## 3. The Agents

### Agent 1: The Planner (`planner_agent`)
- **Role:** Methodical Kubernetes SRE (`google.adk.agents.Agent`).
- **Goal:** Analyze crash logs, query K8s docs, and build a logical debugging plan written to `session.state["planner_checklist"]`.
- **Tools:** `search_kubernetes_documentation` via MCP Server (`mcp-k8s-docs-server` over stdio/SSE).

### Agent 2: The Executor (`executor_agent`)
- **Role:** Deterministic Kubernetes CLI Generator (`google.adk.agents.Agent`).
- **Goal:** Translate `{planner_checklist}` into precise `kubectl` commands using `output_schema=TroubleshootingPlan` (`session.state["troubleshooting_plan"]`).

### Orchestrator & Safety Guardian (`root_orchestrator` & `SafetyGuardian`)
- **Orchestrator:** `root_orchestrator` (`google.adk.agents.SequentialAgent`) executes `planner_agent` $\rightarrow$ `executor_agent`.
- **Role:** Production Risk Monitor (`SafetyGuardian` invoked in `executor_after_callback`).
- **Goal:** Intercept commands and map them against this exact Risk Matrix:
  - **LOW:** `get`, `describe`, `logs`, `top`, `events` (read-only)
  - **MEDIUM:** `restart`, `scale`, `set`, `patch`, `edit`, `cordon`, `uncordon`, `taint`, `label`, `annotate` (modifies runtime state, doesn't delete config)
  - **HIGH:** `delete`, `apply`, `replace`, `drain` (modifies/deletes config) -> *Must inject warning text.*

## 4. The Data Schemas
Ensure `executor_agent` strictly adheres to these models:

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class KubectlCommand(BaseModel):
    step_number: int = Field(description="The sequence step number")
    title: str = Field(description="Title of the step")
    command: str = Field(description="The exact kubectl command to execute")
    explanation: str = Field(description="Detailed explanation of what this command does")
    danger_level: str = Field(description="LOW, MEDIUM, or HIGH")
    alternative_command: Optional[str] = Field(None, description="Safe read-only alternative")

class TroubleshootingPlan(BaseModel):
    problem_summary: str = Field(description="Summary of the analyzed problem")
    error_type: Optional[str] = Field("GeneralClusterAnomaly", description="Classified root-cause Kubernetes cluster error category")
    steps: List[KubectlCommand] = Field(description="List of kubectl command steps in order")
    source_citations: List[str] = Field(description="URLs/names of K8s documents referenced")
```

