"""Testing & Evaluation Framework for the Kubernetes Troubleshooting Copilot.

Includes:
1. Schema Validation Tests (50 diverse queries -> 100% Pydantic parsing via POST /api/v1/diagnose).
2. Heuristic Command Verification (Comprehensive command corpus safety classification via SafetyGuardian).
3. Semantic Evaluation (Faithfulness/Relevance scoring over 150 golden failure scenarios >= 90% via Gemini Flash Judge).
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any

import httpx
import pytest
from google import genai
from google.genai import types

# Ensure backend root is on sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.models import (
    TroubleshootingPlan,
    KubectlCommand,
    IncidentState,
)
from src.guardrails import SafetyGuardian
from src.agents import (
    RETRY_OPTIONS,
    planner_agent,
    run_agent_pipeline,
)
from main import app

DATA_DIR = Path(__file__).resolve().parent / "data"
EVAL_CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "8"))


# ============================================================================
# 1. Schema Validation Tests (50 Diverse Queries -> Backend Pipeline)
# ============================================================================

@pytest.mark.asyncio
async def test_pydantic_schema_compliance():
    """Send 50 diverse queries to POST /api/v1/diagnose and assert 100% TroubleshootingPlan schema compliance."""
    queries: List[str] = json.loads((DATA_DIR / "eval_queries_50.json").read_text(encoding="utf-8"))
    assert len(queries) == 50

    semaphore = asyncio.Semaphore(EVAL_CONCURRENCY)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        timeout=300.0,
    ) as client:

        async def _evaluate_query(idx: int, query: str) -> None:
            async with semaphore:
                response = await client.post(
                    "/api/v1/diagnose",
                    json={"raw_logs": query, "incident_id": f"inc-eval-{idx:03d}"},
                )
                assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
                payload = response.json()
                assert payload.get("success") is True, f"Pipeline error: {payload.get('error')}"
                assert payload.get("plan") is not None, "Missing 'plan' in backend response"

                plan = TroubleshootingPlan.model_validate(payload["plan"])
                assert len(plan.steps) >= 1
                assert plan.problem_summary.strip()
                assert len(plan.source_citations) >= 1

        await asyncio.gather(*(_evaluate_query(idx, q) for idx, q in enumerate(queries, 1)))


# ============================================================================
# 2. Heuristic Command Verification (Broad Command Corpus)
# ============================================================================

def test_command_safety_classification():
    """Verify that commands generated are strictly and accurately classified against the safety risk matrix.

    Risk Matrix:
    - HIGH: delete, apply, replace (modifies/deletes config) -> Injects warning text.
    - MEDIUM: restart, scale (modifies runtime state, does not delete config).
    - LOW: get, describe, logs, top, exec, auth (read-only / non-destructive queries).
    """
    command_test_cases = [
        # --- High Risk (Destructive / Mutating Config) ---
        ("kubectl delete pod payment-api-123 -n prod", "HIGH", True),
        ("kubectl delete deployment auth-service -n default --force", "HIGH", True),
        ("kubectl delete pvc data-disk-0 -n db", "HIGH", True),
        ("kubectl delete namespace staging", "HIGH", True),
        ("kubectl apply -f /tmp/fix-deployment.yaml", "HIGH", True),
        ("kubectl apply -k ./overlays/production", "HIGH", True),
        ("kubectl replace -f configmap.yaml --force", "HIGH", True),
        ("kubectl replace --save-config -f service.yaml", "HIGH", True),

        # --- Medium Risk (Runtime State Modification) ---
        ("kubectl rollout restart deployment/auth-api -n prod", "MEDIUM", False),
        ("kubectl rollout restart daemonset/fluentbit -n kube-system", "MEDIUM", False),
        ("kubectl scale deployment/web-server --replicas=10 -n prod", "MEDIUM", False),
        ("kubectl scale statefulset/redis-cluster --replicas=3 -n default", "MEDIUM", False),

        # --- Low Risk (Read-Only Diagnostics) ---
        ("kubectl get pods -n kube-system", "LOW", False),
        ("kubectl get events --sort-by=.metadata.creationTimestamp", "LOW", False),
        ("kubectl get pvc,pv -A", "LOW", False),
        ("kubectl describe pod coredns-555 -n kube-system", "LOW", False),
        ("kubectl describe node gke-worker-01", "LOW", False),
        ("kubectl logs -f pod/ingress-controller -n ingress-nginx", "LOW", False),
        ("kubectl logs --tail=100 -l app=payment -n prod", "LOW", False),
        ("kubectl top nodes", "LOW", False),
        ("kubectl top pods -A", "LOW", False),
        ("kubectl auth can-i create pods --as=system:serviceaccount:default:crawler", "LOW", False),
    ]

    for cmd_str, expected_danger, expected_warning in command_test_cases:
        inverted_level = "LOW" if expected_danger == "HIGH" else "HIGH"
        cmd_obj = KubectlCommand(
            step_number=1,
            title="Test Step",
            command=cmd_str,
            explanation="Initial explanation text.",
            danger_level=inverted_level,
        )

        evaluated = SafetyGuardian.evaluate_command(cmd_obj)
        assert evaluated.danger_level == expected_danger, (
            f"Failed on command: '{cmd_str}'. Expected {expected_danger}, got {evaluated.danger_level}"
        )

        if expected_warning:
            assert SafetyGuardian.WARNING_TEXT in evaluated.explanation
        else:
            assert "WARNING: Destructive action" not in evaluated.explanation


# ============================================================================
# 3. Semantic Evaluation (Faithfulness & Relevance >= 90% Benchmark)
# ============================================================================

async def _score_plan_with_flash_judge(
    judge_client: genai.Client,
    scenario: Dict[str, Any],
    checklist_steps: List[str],
) -> float:
    """Use Gemini 2.5 Flash LLM-as-a-Judge to score the relevance of `planner_agent`'s checklist (0.0 to 1.0)."""
    prompt = (
        "You are an expert Kubernetes SRE Judge evaluating a diagnostic checklist.\n"
        f"Scenario Category: {scenario['category']}\n"
        f"Raw Logs: {scenario['raw_logs']}\n"
        f"Expected Root Cause: {scenario.get('expected_root_cause', '')}\n"
        f"Mandatory Debugging Keywords: {', '.join(scenario['mandatory_debugging_keywords'])}\n"
        f"Ground Truth Steps: {'; '.join(scenario.get('ground_truth_steps', []))}\n"
        f"Candidate Planner Checklist:\n" + "\n".join(checklist_steps) + "\n\n"
        "Score how well the Candidate Planner Checklist covers the root cause, mandatory debugging "
        "concepts, and ground truth diagnostic path on a scale from 0.0 to 1.0.\n"
        "Return strict JSON: {\"score\": <float between 0.0 and 1.0>}"
    )
    response = await judge_client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return float(json.loads(response.text)["score"])


@pytest.mark.asyncio
async def test_planner_relevance_score():
    """Evaluate `planner_agent` across 150 golden scenarios and assert >= 90% relevance via Gemini Flash judge."""
    scenarios: List[Dict[str, Any]] = json.loads(
        (DATA_DIR / "golden_scenarios_150.json").read_text(encoding="utf-8")
    )
    assert len(scenarios) == 150

    judge_client = genai.Client(http_options=types.HttpOptions(retry_options=RETRY_OPTIONS))
    semaphore = asyncio.Semaphore(EVAL_CONCURRENCY)

    async def _evaluate_scenario(scenario: Dict[str, Any]) -> float:
        async with semaphore:
            state = IncidentState(
                incident_id=scenario["scenario_id"],
                raw_logs=scenario["raw_logs"],
                cluster_context=scenario["cluster_context"],
            )
            updated_state = await run_agent_pipeline(state, agent=planner_agent)
            assert updated_state.status == "PLANNING_COMPLETED"
            assert updated_state.planner_checklist

            return await _score_plan_with_flash_judge(
                judge_client,
                scenario,
                updated_state.planner_checklist,
            )

    scores = await asyncio.gather(*(_evaluate_scenario(sc) for sc in scenarios))
    pass_rate = sum(1 for s in scores if s >= 0.90) / len(scores)
    mean_score = sum(scores) / len(scores)
    print(f"\n[Eval Summary] 150 Golden Scenarios: pass_rate={pass_rate:.1%}, mean_score={mean_score:.3f}")
    assert pass_rate >= 0.90, f"Pass rate {pass_rate:.1%} is below the required 90% threshold"

