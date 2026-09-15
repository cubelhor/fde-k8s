"""Deterministic Safety Guardian for Kubernetes Troubleshooting Copilot.

Enforces static command safety policies and danger level mapping.
"""

import re
from src.models import KubectlCommand


class SafetyGuardian:
    """Production Risk Monitor and Safety Guardrail.
    
    Risk Matrix:
    - HIGH: delete, apply, replace (modifies/deletes config) -> Injects warning text.
    - MEDIUM: restart, scale (modifies runtime state, does not delete config).
    - LOW: get, describe, logs, etc. (read-only queries).
    """

    HIGH_RISK_PATTERN = re.compile(r"\b(delete|apply|replace)\b", re.IGNORECASE)
    MEDIUM_RISK_PATTERN = re.compile(r"\b(restart|scale)\b", re.IGNORECASE)
    WARNING_TEXT = " ⚠️ WARNING: Destructive action."

    @staticmethod
    def evaluate_command(command_obj: KubectlCommand) -> KubectlCommand:
        """Evaluate a KubectlCommand against the risk matrix, correcting danger level and appending warnings.
        
        Args:
            command_obj: KubectlCommand object to evaluate.
            
        Returns:
            The modified KubectlCommand object with verified danger_level and explanation.
        """
        cmd_str = command_obj.command

        if SafetyGuardian.HIGH_RISK_PATTERN.search(cmd_str):
            command_obj.danger_level = "HIGH"
            if SafetyGuardian.WARNING_TEXT not in command_obj.explanation:
                command_obj.explanation += SafetyGuardian.WARNING_TEXT
        elif SafetyGuardian.MEDIUM_RISK_PATTERN.search(cmd_str):
            command_obj.danger_level = "MEDIUM"
        else:
            command_obj.danger_level = "LOW"

        return command_obj
