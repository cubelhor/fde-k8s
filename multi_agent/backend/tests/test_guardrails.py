"""Unit tests for the SafetyGuardian guardrail engine."""

import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.models import KubectlCommand
from src.guardrails import SafetyGuardian


def test_high_risk_command_correction():
    """Test that destructive commands (delete, apply, replace) are flagged as HIGH risk and warning is injected."""
    # 1. Fake command with delete but incorrectly tagged as LOW
    cmd_delete = KubectlCommand(
        step_number=1,
        title="Delete pod",
        command="kubectl delete pod failing-api-pod-7bf8 -n default",
        explanation="Deletes the crashing pod to force recreation.",
        danger_level="LOW",
        alternative_command="kubectl get pod failing-api-pod-7bf8"
    )

    evaluated = SafetyGuardian.evaluate_command(cmd_delete)
    assert evaluated.danger_level == "HIGH"
    assert evaluated.explanation.endswith(" ⚠️ WARNING: Destructive action.")

    # Verify idempotency: running again should not duplicate warning
    evaluated_again = SafetyGuardian.evaluate_command(evaluated)
    assert evaluated_again.danger_level == "HIGH"
    assert evaluated_again.explanation.count("⚠️ WARNING: Destructive action.") == 1

    # 2. Test apply and replace commands
    cmd_apply = KubectlCommand(
        step_number=2,
        title="Apply manifest",
        command="kubectl apply -f deployment.yaml",
        explanation="Applies updated deployment spec.",
        danger_level="LOW"
    )
    evaluated_apply = SafetyGuardian.evaluate_command(cmd_apply)
    assert evaluated_apply.danger_level == "HIGH"
    assert " ⚠️ WARNING: Destructive action." in evaluated_apply.explanation

    cmd_replace = KubectlCommand(
        step_number=3,
        title="Replace config",
        command="kubectl replace --force -f configmap.yaml",
        explanation="Replaces existing configmap.",
        danger_level="LOW"
    )
    evaluated_replace = SafetyGuardian.evaluate_command(cmd_replace)
    assert evaluated_replace.danger_level == "HIGH"
    assert " ⚠️ WARNING: Destructive action." in evaluated_replace.explanation


def test_medium_risk_command_correction():
    """Test that state-modifying but non-destructive commands (restart, scale) are set to MEDIUM risk."""
    # 1. Test rollout restart command incorrectly tagged as LOW
    cmd_restart = KubectlCommand(
        step_number=1,
        title="Restart deployment",
        command="kubectl rollout restart deployment auth-service -n production",
        explanation="Triggers a rolling restart of all auth-service replicas.",
        danger_level="LOW"
    )
    evaluated_restart = SafetyGuardian.evaluate_command(cmd_restart)
    assert evaluated_restart.danger_level == "MEDIUM"
    assert " ⚠️ WARNING" not in evaluated_restart.explanation

    # 2. Test scale command incorrectly tagged as HIGH
    cmd_scale = KubectlCommand(
        step_number=2,
        title="Scale deployment",
        command="kubectl scale deployment worker --replicas=5 -n default",
        explanation="Increases worker replica count to handle queue backlog.",
        danger_level="HIGH"
    )
    evaluated_scale = SafetyGuardian.evaluate_command(cmd_scale)
    assert evaluated_scale.danger_level == "MEDIUM"
    assert " ⚠️ WARNING" not in evaluated_scale.explanation


def test_low_risk_command_correction():
    """Test that read-only commands (get, describe, logs) are set to LOW risk."""
    # 1. Test get command incorrectly tagged as HIGH
    cmd_get = KubectlCommand(
        step_number=1,
        title="Get pods",
        command="kubectl get pods -n kube-system",
        explanation="Inspects running pods in kube-system namespace.",
        danger_level="HIGH"
    )
    evaluated_get = SafetyGuardian.evaluate_command(cmd_get)
    assert evaluated_get.danger_level == "LOW"
    assert " ⚠️ WARNING" not in evaluated_get.explanation

    # 2. Test describe command incorrectly tagged as MEDIUM
    cmd_describe = KubectlCommand(
        step_number=2,
        title="Describe pod",
        command="kubectl describe pod/coredns-555 -n kube-system",
        explanation="Retrieves detailed pod events and conditions.",
        danger_level="MEDIUM"
    )
    evaluated_describe = SafetyGuardian.evaluate_command(cmd_describe)
    assert evaluated_describe.danger_level == "LOW"

    # 3. Test logs command incorrectly tagged as HIGH
    cmd_logs = KubectlCommand(
        step_number=3,
        title="View logs",
        command="kubectl logs --tail=100 -l app=payment -n prod",
        explanation="Streams tail logs from payment containers.",
        danger_level="HIGH"
    )
    evaluated_logs = SafetyGuardian.evaluate_command(cmd_logs)
    assert evaluated_logs.danger_level == "LOW"
