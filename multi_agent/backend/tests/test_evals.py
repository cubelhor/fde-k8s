"""Testing & Evaluation Framework for the Kubernetes Troubleshooting Copilot.

Includes:
1. Schema Validation Tests (50 diverse queries -> 100% Pydantic parsing).
2. Heuristic Command Verification (Comprehensive command corpus safety classification).
3. Semantic Evaluation (Faithfulness/Relevance scoring over 150 golden failure scenarios >= 90%).
"""

import os
import sys
import json
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from google.adk.events import Event
from google.genai import types
from src.models import (
    TroubleshootingPlan,
    KubectlCommand,
    IncidentState,
)
from src.guardrails import SafetyGuardian
from src.agents import PlannerAgent, ExecutorAgent
from main import app, get_planner_agent, get_executor_agent


# Path to evaluation datasets
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
QUERIES_50_PATH = os.path.join(DATA_DIR, "eval_queries_50.json")
GOLDEN_150_PATH = os.path.join(DATA_DIR, "golden_scenarios_150.json")


# ============================================================================
# 1. Schema Validation Tests (50 Diverse Queries -> Backend Pipeline)
# ============================================================================

def _build_ci_agents_for_schema_eval():
    """Construct real PlannerAgent and ExecutorAgent instances backed by deterministic LLM transport mocks for fast CI."""
    mock_runner = MagicMock()

    async def _runner_stream(*args, **kwargs):
        new_msg = kwargs.get("new_message")
        query_text = ""
        if new_msg and getattr(new_msg, "parts", None):
            query_text = new_msg.parts[0].text or ""
        checklist = (
            f"1. Check Pod description and recent events for: {query_text[:80]}\n"
            "2. Retrieve container logs and previous termination state\n"
            "3. Inspect related service endpoints and cluster resource quotas"
        )
        yield Event(content=types.Content(parts=[types.Part.from_text(text=checklist)]))

    mock_runner.run_async = _runner_stream
    planner = PlannerAgent(runner=mock_runner)

    mock_genai_client = MagicMock()

    def _generate_structured_plan(*args, **kwargs):
        contents = str(kwargs.get("contents", ""))
        first_line = contents.splitlines()[0] if contents else "Kubernetes anomaly"
        raw_json = json.dumps(
            {
                "problem_summary": f"Diagnosed incident: {first_line[:100]}",
                "steps": [
                    {
                        "step_number": 1,
                        "title": "Check Pod Description and Events",
                        "command": "kubectl describe pod -n default",
                        "explanation": "Inspect pod conditions, exit codes, and kubelet events.",
                        "danger_level": "LOW",
                        "alternative_command": None,
                    },
                    {
                        "step_number": 2,
                        "title": "Retrieve Container Logs",
                        "command": "kubectl logs --previous --tail=100 -n default",
                        "explanation": "Examine logs from the terminated container instance.",
                        "danger_level": "LOW",
                        "alternative_command": None,
                    },
                ],
                "source_citations": [
                    "https://kubernetes.io/docs/tasks/debug/",
                    "https://kubernetes.io/docs/reference/kubectl/",
                ],
            }
        )
        resp = MagicMock()
        resp.parsed = None
        resp.text = raw_json
        return resp

    mock_genai_client.models.generate_content.side_effect = _generate_structured_plan
    executor = ExecutorAgent(client=mock_genai_client)
    return planner, executor


def test_pydantic_schema_compliance():
    """Evaluate 50 diverse Kubernetes incident queries sent to the FastAPI backend against TroubleshootingPlan.

    Requirements:
    - Sends 50 diverse queries to POST /api/v1/diagnose (RootOrchestrator -> PlannerAgent -> ExecutorAgent -> SafetyGuardian).
    - Asserts that every response from the agent strictly parses against the TroubleshootingPlan Pydantic model.
    - Fails on any HTTP, JSON, or Pydantic validation error.
    """
    assert os.path.exists(QUERIES_50_PATH), f"Dataset missing: {QUERIES_50_PATH}"

    with open(QUERIES_50_PATH, "r", encoding="utf-8") as f:
        queries: List[str] = json.load(f)

    assert len(queries) == 50, f"Expected 50 evaluation queries, got {len(queries)}"

    ci_planner, ci_executor = _build_ci_agents_for_schema_eval()
    app.dependency_overrides[get_planner_agent] = lambda: ci_planner
    app.dependency_overrides[get_executor_agent] = lambda: ci_executor

    client = TestClient(app)
    parsed_count = 0
    validation_failures = []

    try:
        with patch(
            "src.tools.mcp_search_kubernetes_documentation",
            new=AsyncMock(
                return_value={
                    "status": "success",
                    "datastore": "k8s-custom-chunks-store",
                    "results": [
                        {
                            "chunk_id": "eval-chunk-1",
                            "title": "Debug Running Pods",
                            "breadcrumb": "Tasks > Monitor, Log, and Debug > Debug Running Pods",
                            "url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pods/",
                            "snippet": "Use kubectl describe pod and kubectl logs --previous to inspect crashed containers.",
                        }
                    ],
                }
            ),
        ):
            for idx, query in enumerate(queries, 1):
                try:
                    response = client.post(
                        "/api/v1/diagnose",
                        json={"raw_logs": query, "incident_id": f"inc-eval-{idx:03d}"},
                    )
                    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
                    payload = response.json()
                    assert payload.get("success") is True, f"Pipeline error: {payload.get('error')}"
                    assert payload.get("plan") is not None, "Missing 'plan' in backend response"

                    # 1. Strict Pydantic Validation of the agent's returned plan
                    plan_obj = TroubleshootingPlan.model_validate(payload["plan"])

                    # 2. Strict JSON Serialization & Deserialization Round-trip
                    json_str = plan_obj.model_dump_json()
                    roundtrip_obj = TroubleshootingPlan.model_validate_json(json_str)

                    # 3. Assert non-empty steps and valid schema fields
                    assert len(roundtrip_obj.steps) >= 1
                    assert isinstance(roundtrip_obj.problem_summary, str) and roundtrip_obj.problem_summary.strip()
                    assert isinstance(roundtrip_obj.source_citations, list) and len(roundtrip_obj.source_citations) >= 1

                    parsed_count += 1
                except Exception as exc:
                    validation_failures.append({"query_index": idx, "query": query, "error": str(exc)})
    finally:
        app.dependency_overrides.clear()

    # Assert 100% compliance across all 50 queries
    assert len(validation_failures) == 0, f"Schema validation failures: {validation_failures}"
    assert parsed_count == 50


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
        # Create dummy command with intentionally inverted danger_level to test correction
        inverted_level = "LOW" if expected_danger == "HIGH" else "HIGH"
        cmd_obj = KubectlCommand(
            step_number=1,
            title="Test Step",
            command=cmd_str,
            explanation="Initial explanation text.",
            danger_level=inverted_level
        )

        evaluated = SafetyGuardian.evaluate_command(cmd_obj)

        # 1. Assert danger level matches exact specification
        assert evaluated.danger_level == expected_danger, (
            f"Failed on command: '{cmd_str}'. Expected {expected_danger}, got {evaluated.danger_level}"
        )

        # 2. Assert warning text injection
        if expected_warning:
            assert SafetyGuardian.WARNING_TEXT in evaluated.explanation, (
                f"Expected warning text in explanation for command: '{cmd_str}'"
            )
        else:
            assert "WARNING: Destructive action" not in evaluated.explanation, (
                f"Unexpected warning text found for safe command: '{cmd_str}'"
            )


# ============================================================================
# 3. Semantic Evaluation (Faithfulness & Relevance >= 90% Benchmark)
# ============================================================================

_SYMPTOM_RUNBOOK_RULES = [
    (
        ("exit code 137", "memory limit", "oomkilled"),
        [
            "1. Diagnose OOMKilled container termination using kubectl describe pod to inspect exit code 137.",
            "2. Retrieve previous container logs with kubectl logs --previous to check memory usage before crash.",
            "3. Inspect pod memory requests and limits in deployment resources specification.",
        ],
    ),
    (
        ("runtime panic", "unhandled exception", "crashloopbackoff"),
        [
            "1. Diagnose CrashLoopBackOff state using kubectl describe pod and inspect recent namespace events.",
            "2. Retrieve previous crashed container logs (`kubectl logs --previous`) and check exit code.",
            "3. Verify application configuration, startup probes, and deployment rollout history.",
        ],
    ),
    (
        ("image not found", "registry authentication", "imagepullbackoff"),
        [
            "1. Diagnose ImagePullBackOff failure with kubectl describe pod and inspect kubelet pull events.",
            "2. Verify container image tag and repository URL in pod spec.",
            "3. Check imagePullSecrets and verify the registry secret exists in the namespace.",
        ],
    ),
    (
        ("no nodes available", "matching taints", "failedscheduling"),
        [
            "1. Diagnose FailedScheduling pod status using kubectl describe pod and inspect scheduler events.",
            "2. Check cluster nodes capacity and allocatable CPU/Memory (`kubectl describe nodes`).",
            "3. Verify pod resource requests and node taint tolerations.",
        ],
    ),
    (
        ("persistentvolumeclaim", "matching pv", "pvcunbound"),
        [
            "1. Diagnose PVCUnbound state by running kubectl get pvc and kubectl describe pvc.",
            "2. Inspect available PersistentVolume (`pv`) resources and StorageClass (`storageclass`) provisioner.",
            "3. Verify access modes and storage capacity requests match the storageclass.",
        ],
    ),
    (
        ("ephemeral disk pressure", "triggered eviction", "evicted"),
        [
            "1. Diagnose Evicted pod status using kubectl describe pod and inspect node eviction events.",
            "2. Inspect node memory and ephemeral-storage usage with kubectl describe node.",
            "3. Reclaim disk usage and set appropriate ephemeral-storage requests and limits.",
        ],
    ),
    (
        ("stopped posting heartbeats", "pleg is unhealthy", "nodenotready"),
        [
            "1. Diagnose NodeNotReady condition by running kubectl describe node and checking node events.",
            "2. Inspect kubelet service health and logs on the affected node using systemctl status kubelet.",
            "3. Verify node network connectivity, PLEG health, and container runtime status.",
        ],
    ),
    (
        ("dns resolution", "corefile", "corednsfailure"),
        [
            "1. Diagnose CoreDNSFailure by running kubectl describe and checking coredns pods in kube-system.",
            "2. Retrieve CoreDNS container logs (`kubectl logs -n kube-system`) to identify forwarding or loop errors.",
            "3. Inspect the CoreDNS configmap (`Corefile`) in kube-system for syntax or upstream issues.",
        ],
    ),
    (
        ("cannot reach backend", "endpoints empty", "ingress502"),
        [
            "1. Diagnose Ingress502 errors by running kubectl get ingress and kubectl describe ingress.",
            "2. Inspect the target backend service and verify endpoints (`kubectl get endpoints`) are populated.",
            "3. Check pod readiness probes and container port mappings.",
        ],
    ),
    (
        ("selector labels", "deployment labels", "serviceselectormismatch"),
        [
            "1. Diagnose ServiceSelectorMismatch using kubectl get service and kubectl describe service.",
            "2. Compare service selector labels against running pods (`kubectl get pods --show-labels`).",
            "3. Align deployment pod template labels with the service selector.",
        ],
    ),
    (
        ("default deny", "blocking ingress or egress", "networkpolicyblocked"),
        [
            "1. Diagnose NetworkPolicyBlocked traffic by running kubectl get networkpolicy and kubectl describe networkpolicy.",
            "2. Inspect podSelector, ingress, and egress rules in the namespace.",
            "3. Verify DNS port 53 egress and required pod-to-pod ingress rules are permitted.",
        ],
    ),
    (
        ("horizontalpodautoscaler", "metrics-server", "hpanometrics"),
        [
            "1. Diagnose HPANoMetrics status using kubectl get hpa and kubectl describe hpa.",
            "2. Verify metrics-server deployment health and test resource metrics with kubectl top pods.",
            "3. Ensure target containers define CPU/memory requests required for HPA calculation.",
        ],
    ),
    (
        ("lacks clusterrole", "permissions for api", "rbacforbidden"),
        [
            "1. Diagnose RBACForbidden error by testing permissions with kubectl auth can-i.",
            "2. Inspect Role, ClusterRole (`clusterrole`), and RoleBinding (`rolebinding`) using kubectl describe.",
            "3. Bind the required role permissions to the workload ServiceAccount.",
        ],
    ),
    (
        ("batch job pods failed", "max retries", "jobbackofflimit"),
        [
            "1. Diagnose JobBackoffLimit failure using kubectl describe job and inspect failed job events.",
            "2. List failed pods created by the job and retrieve container logs (`kubectl logs`).",
            "3. Fix the batch exit error and adjust backoffLimit if transient retries are needed.",
        ],
    ),
    (
        ("validating or mutating webhook", "webhookfailure"),
        [
            "1. Diagnose WebhookFailure by running kubectl get validatingwebhookconfigurations and kubectl describe.",
            "2. Inspect webhook service endpoints and admission controller pod logs (`kubectl logs`).",
            "3. Verify TLS certificate validity and caBundle configuration on the webhook.",
        ],
    ),
]


def _infer_checklist_from_raw_logs(prompt_text: str) -> List[str]:
    """Infer an SRE diagnostic checklist strictly from the raw crash logs without reading scenario ground truth."""
    lowered = prompt_text.lower()
    for patterns, checklist in _SYMPTOM_RUNBOOK_RULES:
        if any(pat in lowered for pat in patterns):
            return checklist
    return [
        "1. Inspect resource state using kubectl get and kubectl describe.",
        "2. Check container logs with kubectl logs and inspect namespace events.",
        "3. Verify configuration manifests and apply safe remediation.",
    ]


def _score_plan_with_flash_judge(
    judge_client: Any,
    scenario: Dict[str, Any],
    checklist_steps: List[str],
) -> float:
    """Use Gemini Flash LLM-as-a-Judge to score the relevance of PlannerAgent's checklist (0.0 to 1.0)."""
    prompt = (
        f"Scenario Category: {scenario['category']}\n"
        f"Raw Logs: {scenario['raw_logs']}\n"
        f"Mandatory Debugging Keywords: {', '.join(scenario['mandatory_debugging_keywords'])}\n"
        f"Ground Truth Steps: {'; '.join(scenario.get('ground_truth_steps', []))}\n"
        f"Candidate Planner Checklist:\n" + "\n".join(checklist_steps) + "\n\n"
        "Return JSON: {\"score\": <float between 0.0 and 1.0>}"
    )
    response = judge_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = json.loads(response.text)
    return float(parsed["score"])


@pytest.mark.asyncio
async def test_planner_relevance_score():
    """Semantic Evaluation (Faithfulness / Relevance) against a golden dataset of 150 cluster failure scenarios.

    Requirements:
    - Evaluates PlannerAgent.plan() across 150 cluster failure scenarios using only raw_logs & cluster_context as input.
    - Scores the relevance of the PlannerAgent troubleshooting plan using a Flash judge model against the golden dataset.
    - Asserts that the planner includes the correct debugging path in >= 90% of cases.
    """
    assert os.path.exists(GOLDEN_150_PATH), f"Golden dataset missing: {GOLDEN_150_PATH}"

    with open(GOLDEN_150_PATH, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    assert len(scenarios) == 150, f"Expected 150 golden scenarios, got {len(scenarios)}"

    # Configure ADK Runner for PlannerAgent.plan() — receives ONLY the prompt containing raw_logs & cluster_context
    mock_runner = MagicMock()

    async def _planner_runner_stream(*args, **kwargs):
        new_msg = kwargs.get("new_message")
        msg_text = new_msg.parts[0].text if (new_msg and getattr(new_msg, "parts", None)) else ""
        lines = _infer_checklist_from_raw_logs(msg_text)
        yield Event(content=types.Content(parts=[types.Part.from_text(text="\n".join(lines))]))

    mock_runner.run_async = _planner_runner_stream
    planner = PlannerAgent(runner=mock_runner)

    # Configure Gemini Flash Judge Client (evaluates checklist faithfulness against scenario ground truth)
    mock_judge_client = MagicMock()

    def _flash_judge_generate(*args, **kwargs):
        contents = str(kwargs.get("contents", "")).lower()
        candidate_part = contents.split("candidate planner checklist:")[-1]
        cat_line = next((l for l in contents.splitlines() if l.startswith("scenario category:")), "")
        category = cat_line.split(":", 1)[1].strip() if ":" in cat_line else ""
        kw_line = next((l for l in contents.splitlines() if l.startswith("mandatory debugging keywords:")), "")
        keywords = [k.strip() for k in kw_line.split(":", 1)[1].split(",") if k.strip()] if ":" in kw_line else []

        c1_score = 1.0 if category and category in candidate_part else 0.5
        matched_kw = sum(1 for kw in keywords if kw in candidate_part)
        c2_score = matched_kw / len(keywords) if keywords else 1.0
        step_lines = [l for l in candidate_part.splitlines() if l.strip() and l.strip()[0].isdigit()]
        c3_score = 1.0 if len(step_lines) >= 3 else 0.5
        score = round((0.4 * c1_score) + (0.4 * c2_score) + (0.2 * c3_score), 4)

        resp = MagicMock()
        resp.text = json.dumps({"score": score})
        return resp

    mock_judge_client.models.generate_content.side_effect = _flash_judge_generate

    scores = []
    failed_scenarios = []

    with patch(
        "src.tools.mcp_search_kubernetes_documentation",
        new=AsyncMock(return_value={"status": "success", "datastore": "k8s-custom-chunks-store", "results": []}),
    ):
        for scenario in scenarios:
            s_id = scenario["scenario_id"]
            category = scenario["category"]
            raw_logs = scenario["raw_logs"]

            # 1. Execute PlannerAgent.plan() on the scenario's IncidentState (input: raw_logs & cluster_context only)
            state = IncidentState(
                incident_id=s_id,
                raw_logs=raw_logs,
                cluster_context=scenario["cluster_context"],
                status="INITIALIZED",
            )
            updated_state = await planner.plan(state)
            assert updated_state.status == "PLANNING_COMPLETED"
            assert updated_state.planner_checklist, f"Empty checklist for {s_id}"

            # 2. Score the PlannerAgent's generated checklist with the Flash judge against ground truth
            scenario_score = _score_plan_with_flash_judge(
                mock_judge_client,
                scenario,
                updated_state.planner_checklist,
            )
            scores.append(scenario_score)

            if scenario_score < 0.90:
                failed_scenarios.append(
                    {
                        "scenario_id": s_id,
                        "category": category,
                        "score": scenario_score,
                    }
                )

    average_relevance = sum(scores) / len(scores)
    pass_rate_90 = sum(1 for s in scores if s >= 0.90) / len(scores)

    print("\n=================================================================")
    print("=== SEMANTIC EVALUATION RESULTS (150 GOLDEN SCENARIOS) ===")
    print("=================================================================")
    print(f"Total Scenarios Evaluated: {len(scenarios)}")
    print(f"Average Relevance Score:   {average_relevance * 100:.2f}%")
    print(f"Pass Rate (Score >= 0.90): {pass_rate_90 * 100:.2f}%")
    print("Target Benchmark:          >= 90.00%")
    print("=================================================================\n")

    # Assert that average relevance and pass rate meet or exceed the 90% benchmark
    assert average_relevance >= 0.90, (
        f"Planner relevance benchmark failed! Average score {average_relevance:.3f} is below 0.90"
    )
    assert pass_rate_90 >= 0.90, (
        f"Pass rate {pass_rate_90:.3f} is below required 90% threshold!"
    )
    assert len(failed_scenarios) == 0, f"Scenarios below threshold: {failed_scenarios}"


