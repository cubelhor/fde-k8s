"""Unit tests for the ExecutorAgent and Structured Output generation."""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.models import TroubleshootingPlan, KubectlCommand
from src.agents import ExecutorAgent


def test_executor_generate_commands_with_safety_interception():
    """Test that ExecutorAgent generates structured commands and SafetyGuardian intercepts and verifies risk levels."""
    mock_client = MagicMock()

    # Raw structured plan returned by Gemini 2.5 Pro with some incorrect danger levels
    mock_raw_plan = TroubleshootingPlan(
        problem_summary="Pod crashing due to Out Of Memory (OOMKilled) error.",
        steps=[
            KubectlCommand(
                step_number=1,
                title="Inspect Pod Details",
                command="kubectl describe pod auth-api-5d7f -n prod",
                explanation="Examines last termination state and memory limits.",
                danger_level="HIGH",  # Incorrectly tagged as HIGH (should be LOW)
                alternative_command=None
            ),
            KubectlCommand(
                step_number=2,
                title="Scale Worker Deployment",
                command="kubectl scale deployment auth-api --replicas=4 -n prod",
                explanation="Increases pod replica count to distribute load.",
                danger_level="LOW",   # Incorrectly tagged as LOW (should be MEDIUM)
                alternative_command=None
            ),
            KubectlCommand(
                step_number=3,
                title="Force Delete Stuck Pod",
                command="kubectl delete pod auth-api-5d7f -n prod --grace-period=0",
                explanation="Deletes the stuck pod forcefully.",
                danger_level="LOW",   # Incorrectly tagged as LOW (should be HIGH + Warning)
                alternative_command="kubectl get pod auth-api-5d7f -n prod"
            ),
        ],
        source_citations=[
            "https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/",
            "https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/"
        ]
    )

    # Setup mock response object with .parsed attribute (native Google GenAI Pydantic support)
    mock_response = MagicMock()
    mock_response.parsed = mock_raw_plan
    mock_response.text = mock_raw_plan.model_dump_json()
    mock_client.models.generate_content.return_value = mock_response

    executor = ExecutorAgent(client=mock_client)
    strategy = "1. Describe the failing pod. 2. Scale deployment. 3. Delete stuck pod."
    
    plan = executor.generate_commands(strategy)

    # 1. Verify that the returned object is a valid TroubleshootingPlan
    assert isinstance(plan, TroubleshootingPlan)
    assert plan.problem_summary == "Pod crashing due to Out Of Memory (OOMKilled) error."
    assert len(plan.steps) == 3
    assert len(plan.source_citations) == 2

    # 2. Verify Gemini API was called with structured output schema & instructions
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"
    assert call_kwargs["contents"] == strategy
    assert call_kwargs["config"].response_mime_type == "application/json"
    assert call_kwargs["config"].response_schema == TroubleshootingPlan

    # 3. Verify SafetyGuardian successfully intercepted and corrected each command
    # Step 1: describe -> corrected from HIGH to LOW
    assert plan.steps[0].danger_level == "LOW"
    assert "⚠️ WARNING" not in plan.steps[0].explanation

    # Step 2: scale -> corrected from LOW to MEDIUM
    assert plan.steps[1].danger_level == "MEDIUM"
    assert "⚠️ WARNING" not in plan.steps[1].explanation

    # Step 3: delete -> corrected from LOW to HIGH and injected warning
    assert plan.steps[2].danger_level == "HIGH"
    assert plan.steps[2].explanation.endswith(" ⚠️ WARNING: Destructive action.")


def test_executor_generate_commands_from_json_text_fallback():
    """Test that ExecutorAgent correctly falls back to parsing response.text when .parsed is None."""
    mock_client = MagicMock()

    json_payload = """
    {
        "problem_summary": "CoreDNS pods failing liveness probe.",
        "steps": [
            {
                "step_number": 1,
                "title": "Check CoreDNS logs",
                "command": "kubectl logs -l k8s-app=kube-dns -n kube-system",
                "explanation": "Inspect DNS query logs.",
                "danger_level": "LOW",
                "alternative_command": null
            },
            {
                "step_number": 2,
                "title": "Apply configmap fix",
                "command": "kubectl apply -f coredns-config.yaml",
                "explanation": "Applies corrected Corefile configmap.",
                "danger_level": "LOW",
                "alternative_command": null
            }
        ],
        "source_citations": ["https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/"]
    }
    """

    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = json_payload
    mock_client.models.generate_content.return_value = mock_response

    executor = ExecutorAgent(client=mock_client)
    plan = executor.generate_commands("Fix CoreDNS resolution failure")

    assert isinstance(plan, TroubleshootingPlan)
    assert len(plan.steps) == 2
    assert plan.steps[0].danger_level == "LOW"
    # Step 2 has 'apply' -> SafetyGuardian corrects to HIGH and appends warning
    assert plan.steps[1].danger_level == "HIGH"
    assert plan.steps[1].explanation.endswith(" ⚠️ WARNING: Destructive action.")
