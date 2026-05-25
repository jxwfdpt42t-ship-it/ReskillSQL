from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptanceDecision:
    accepted: bool
    reason: str


class AcceptancePolicy:
    """First acceptance policy.

    This is intentionally conservative for now: only accept immediately when the
    user passes --apply-skill-patch. The next layer will compare before/after
    validation accuracy and use this policy to decide whether to keep the edit.
    """

    def decide(
        self,
        apply_requested: bool,
        patch_text: str,
        before_accuracy: float | None = None,
        after_accuracy: float | None = None,
        min_delta: float = 0.0,
    ) -> AcceptanceDecision:
        if not patch_text:
            return AcceptanceDecision(False, "no_patch_generated")
        if before_accuracy is not None and after_accuracy is not None:
            delta = after_accuracy - before_accuracy
            if delta >= min_delta:
                return AcceptanceDecision(True, f"validation_passed_delta={delta:.4f}")
            return AcceptanceDecision(False, f"validation_failed_delta={delta:.4f}")
        if apply_requested:
            return AcceptanceDecision(True, "manual_apply_requested")
        return AcceptanceDecision(False, "dry_run")
