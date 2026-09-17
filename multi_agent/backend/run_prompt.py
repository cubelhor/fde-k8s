"""Interactive CLI runner to test the end-to-end Kubernetes Troubleshooting Copilot pipeline with any prompt.

Usage:
    .venv/bin/python multi_agent/backend/run_prompt.py "Pod payment-api-6d8f9b in namespace prod is stuck in CrashLoopBackOff (exit code 137 / OOMKilled)"
"""

import sys
import json
import asyncio
import argparse
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.models import IncidentState
from src.agents import RootOrchestrator


async def run_end_user_prompt(prompt: str, cluster_context: str = "gke-prod-eu / namespace: prod") -> None:
    print("=" * 80)
    print(f"USER PROMPT: {prompt}")
    print(f"CONTEXT    : {cluster_context}")
    print("=" * 80)

    state = IncidentState(
        incident_id="inc-cli-test-001",
        raw_logs=prompt,
        cluster_context=cluster_context,
    )

    orchestrator = RootOrchestrator()
    final_state = await orchestrator.orchestrate(state)

    print("\n[1] ORCHESTRATOR STATUS TRANSITIONS:")
    print("    " + " -> ".join(final_state.metadata.get("status_history", [])))
    print(f"    Final Status: {final_state.status}")

    print("\n[2] RETRIEVED KUBERNETES DOC CITATIONS (via mcp-k8s-docs-server):")
    for idx, citation in enumerate(final_state.source_citations or [], 1):
        print(f"    {idx}. {citation}")

    print("\n[3] PLANNER AGENT DIAGNOSTIC CHECKLIST:")
    for line in (final_state.planner_checklist or [])[:8]:
        print(f"    {line}")

    print("\n[4] EXECUTOR AGENT + SAFETY GUARDIAN VALIDATED KUBECTL COMMANDS:")
    for step in final_state.final_validated_command or []:
        print(f"    Step {step.step_number} [{step.danger_level}] - {step.title}")
        print(f"      Command     : {step.command}")
        print(f"      Explanation : {step.explanation}")
        if step.alternative_command:
            print(f"      Safe Alt    : {step.alternative_command}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the K8s Troubleshooting Copilot with a simple end-user prompt.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Pod payment-api-6d8f9b in namespace prod is stuck in CrashLoopBackOff (exit code 137 / OOMKilled) after a memory spike.",
        help="End-user Kubernetes crash log or troubleshooting query",
    )
    parser.add_argument("--context", default="gke-prod-eu / namespace: prod", help="Cluster and namespace context")
    args = parser.parse_args()
    asyncio.run(run_end_user_prompt(args.prompt, args.context))
