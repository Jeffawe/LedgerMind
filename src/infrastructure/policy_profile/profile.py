from __future__ import annotations

from typing import Any

class PolicyProfileStore:
    """MVP policy profile store with a single hardcoded default profile."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {
            "default_v1": {
                "id": "default_v1",
                "risk_tolerance": "conservative",
                "budgeting_style": "zero-based",
                "communication_style": "concise",
                "priorities": [
                    "cashflow_stability",
                    "grounded_recommendations",
                    "low_regret_actions",
                ],
                "rules": [
                    "Prefer deterministic tool evidence over inference.",
                    "Label estimated savings as assumptions.",
                    "Protect liquidity before optimization.",
                ],
            }
        }

    def fetch_policy_profile(self, profile_id: str) -> dict[str, Any]:
        return self._profiles.get(profile_id, self._profiles["default_v1"])

