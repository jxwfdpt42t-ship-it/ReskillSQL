from __future__ import annotations


class PatchBudget:
    """Limit how much long-term skill text can change in one evolution step."""

    def __init__(self, max_rules: int = 3) -> None:
        if max_rules <= 0:
            raise ValueError("max_rules must be positive")
        self.max_rules = max_rules

    def clip(self, patch_text: str) -> tuple[str, dict]:
        if not patch_text.strip():
            return "", {"max_rules": self.max_rules, "kept_rules": 0, "original_rules": 0}

        lines = patch_text.strip().splitlines()
        kept: list[str] = []
        original_rules = 0
        kept_rules = 0
        for line in lines:
            is_rule = line.startswith("- ") or line.startswith("* ")
            if is_rule:
                original_rules += 1
                if kept_rules >= self.max_rules:
                    continue
                kept_rules += 1
            elif original_rules > kept_rules and line.startswith("  - "):
                continue
            kept.append(line)

        clipped = "\n".join(kept).rstrip() + "\n"
        return clipped, {
            "max_rules": self.max_rules,
            "kept_rules": kept_rules,
            "original_rules": original_rules,
            "clipped": original_rules > kept_rules,
        }
