"""Shared data models."""

from dataclasses import dataclass, field
from typing import Optional


FIELD_LABELS_HE: dict[str, str] = {
    "summary": "כותרת (Summary)",
    "steps_to_reproduce": "צעדים לשחזור (Steps to Reproduce)",
    "expected_result": "תוצאה מצופה (Expected Result)",
    "actual_result": "מה שקורה בפועל (Actual Result)",
}


@dataclass
class BugDraft:
    summary: str = ""
    steps_to_reproduce: str = ""
    expected_result: str = ""
    actual_result: str = ""
    duplicate_warning: Optional[str] = None
    needs_more_info: bool = False
    info_request_he: str = ""
    missing_fields: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        parts: list[str] = []
        if self.duplicate_warning:
            parts.append(f"> **Possible duplicate:** {self.duplicate_warning}\n")
        parts.extend(
            [
                f"## Summary\n{self.summary}",
                f"## Steps to Reproduce\n{self.steps_to_reproduce}",
                f"## Expected Result\n{self.expected_result}",
                f"## Actual Result\n{self.actual_result}",
            ]
        )
        return "\n\n".join(parts)

    def missing_required_labels(self) -> list[str]:
        missing: list[str] = []
        for key, label in FIELD_LABELS_HE.items():
            if not getattr(self, key, "").strip():
                missing.append(label)
        return missing

    def is_complete(self) -> bool:
        return not self.missing_required_labels()

    @classmethod
    def from_dict(cls, data: dict) -> "BugDraft":
        def pick(*keys: str) -> str:
            for key in keys:
                value = data.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return ""

        missing_raw = data.get("missing_fields") or []
        missing_fields = [str(item) for item in missing_raw] if isinstance(missing_raw, list) else []

        return cls(
            summary=pick("summary", "title"),
            steps_to_reproduce=pick(
                "steps_to_reproduce",
                "stepsToReproduce",
                "steps",
                "reproduction_steps",
            ),
            expected_result=pick("expected_result", "expectedResult", "expected"),
            actual_result=pick("actual_result", "actualResult", "actual"),
            duplicate_warning=data.get("duplicate_warning") or data.get("duplicateWarning"),
            needs_more_info=bool(data.get("needs_more_info") or data.get("needsMoreInfo")),
            info_request_he=str(
                data.get("info_request_he")
                or data.get("info_request")
                or data.get("user_message_hebrew")
                or ""
            ).strip(),
            missing_fields=missing_fields,
        )
