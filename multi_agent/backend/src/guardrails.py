"""Deterministic Safety Guardian for Kubernetes Troubleshooting Copilot.

Enforces static command safety policies and danger level mapping.
"""

import re
from src.models import KubectlCommand


class SafetyGuardian:
    """Production Risk Monitor and Safety Guardrail (Sole Deterministic Authority).

    Risk Matrix (Fail-Closed):
    - HIGH: delete, apply, replace, drain (modifies/deletes config or evicts nodes) -> Injects warning text.
    - LOW: Explicit read-only allowlist (get, describe, logs, top, events, explain, version, cluster-info, api-resources, api-versions, diff, auth can-i).
    - MEDIUM: Any other runtime state modification or unlisted kubectl subcommand (restart, scale, set, patch, edit, cordon, uncordon, taint, label, annotate, exec, cp, debug, etc.).
    """

    HIGH_RISK_PATTERN = re.compile(r"\b(delete|apply|replace|drain)\b", re.IGNORECASE)
    MEDIUM_RISK_PATTERN = re.compile(
        r"\b(restart|scale|set|patch|edit|cordon|uncordon|taint|label|annotate|autoscale|cp|debug)\b",
        re.IGNORECASE,
    )
    LOW_RISK_PATTERN = re.compile(
        r"^\s*kubectl\s+(get|describe|logs|top|events|explain|version|cluster-info|api-resources|api-versions|diff|exec|auth\s+can-i)\b",
        re.IGNORECASE,
    )
    WARNING_TEXT = " ⚠️ WARNING: Destructive action."

    @staticmethod
    def evaluate_command(command_obj: KubectlCommand) -> KubectlCommand:
        """Evaluate a KubectlCommand against the fail-closed risk matrix, correcting danger level and appending warnings."""
        cmd_str = command_obj.command

        if SafetyGuardian.HIGH_RISK_PATTERN.search(cmd_str):
            command_obj.danger_level = "HIGH"
            if SafetyGuardian.WARNING_TEXT not in command_obj.explanation:
                command_obj.explanation += SafetyGuardian.WARNING_TEXT
        elif SafetyGuardian.MEDIUM_RISK_PATTERN.search(cmd_str):
            command_obj.danger_level = "MEDIUM"
        elif SafetyGuardian.LOW_RISK_PATTERN.search(cmd_str):
            command_obj.danger_level = "LOW"
        else:
            command_obj.danger_level = "MEDIUM"

        return command_obj

