# Project: Kubernetes Troubleshooting Copilot

## 1. System Overview
We are building a high-performance, context-grounded agentic platform to assist SREs in debugging K8s anomalies. It uses a decoupled Planner-Executor architecture, enforces strict schema compliance via Pydantic, and features a determinist safety guardrail.

**State Management:** Use a Pydantic `IncidentState` class to pass data between the agents tracking `raw_logs`, `planner_checklist`, `raw_command`, and `final_validated_command`.

## 2. Tech Stack & Infrastructure
- **Framework:** ADK (Agent Development Kit)
- **Runtime:** FastAPI (Cloud Run)
- **Language:** Python 3.11+
- **LLM:** Gemini 2.5 Pro
- **Validation:** Pydantic (Strict Schema Enforcement)
- **Observability:** OpenTelemetry (OTEL) traces to Cloud Trace; token metrics to BigQuery; user feedback to Firestore.

## 3. The Agents

### Agent 1: The Planner (PlannerAgent)
- **Role:** Methodical Kubernetes SRE.
- **Goal:** Analyze crash logs, query K8s docs, and build a logical debugging plan.
- **Tools:** `search_kubernetes_documentation` via MCP Server (`mcp-k8s-docs-server` over stdio/SSE).

### Agent 2: The Executor (ExecutorAgent)
- **Role:** Deterministic Kubernetes CLI Generator.
- **Goal:** Translate the Planner's abstract steps into precise `kubectl` commands. Must output JSON matching the exact schema below.

### Agent 3: The Safety Guardian (SafetyGuardian)
- **Role:** Production Risk Monitor.
- **Goal:** Intercept commands and map them against this exact Risk Matrix:
  - **LOW:** `get`, `describe`, `logs` (read-only)
  - **MEDIUM:** `restart`, `scale` (modifies state, doesn't delete)
  - **HIGH:** `delete`, `apply`, `replace` (modifies/deletes config) -> *Must inject warning text.*

## 4. The Data Schemas
Ensure the ExecutorAgent strictly adheres to these models:

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
    steps: List[KubectlCommand] = Field(description="List of kubectl command steps in order")
    source_citations: List[str] = Field(description="URLs/names of K8s documents referenced")
