"""Build a complete bug draft from the user's free-text description."""

from __future__ import annotations

import re

from nexus_toolkit.models import BugDraft

_STEPS_HEADERS = re.compile(
    r"^(?:צעדים|שלבים|שחזור|steps(?:\s+to\s+reproduce)?|reproduction)\s*:?\s*",
    re.IGNORECASE,
)
_EXPECTED_HEADERS = re.compile(
    r"^(?:מצופה|צפוי|אמור|מה\s+אמור|expected(?:\s+result)?|should)\s*:?\s*",
    re.IGNORECASE,
)
_ACTUAL_HEADERS = re.compile(
    r"^(?:בפועל|מה\s+קורה|קורה\s+בפועל|actual(?:\s+result)?|instead)\s*:?\s*",
    re.IGNORECASE,
)
_NUMBERED_STEP = re.compile(r"^\s*(?:\d+[\.\)]|[-*•])\s+(.+)$")
_VS_SPLIT = re.compile(r"\s+(?:אבל|אך|במקום|however|but|instead)\s+", re.IGNORECASE)


def build_local_draft_from_description(description: str) -> BugDraft:
    """Build a full draft from free text — structured or a single sentence."""
    text = description.strip()
    if not text:
        return BugDraft()

    extracted = extract_fields_from_description(text)
    return BugDraft(
        summary=extracted.get("summary") or _first_sentence(text),
        steps_to_reproduce=extracted.get("steps_to_reproduce", ""),
        expected_result=extracted.get("expected_result", ""),
        actual_result=extracted.get("actual_result", ""),
    )


def extract_fields_from_description(description: str) -> dict[str, str]:
    """Parse structured hints or infer all fields from free text."""
    text = description.strip()
    if not text:
        return {}

    found: dict[str, str] = {}
    lines = text.splitlines()

    current: str | None = None
    buffers: dict[str, list[str]] = {
        "steps_to_reproduce": [],
        "expected_result": [],
        "actual_result": [],
    }
    numbered_steps: list[str] = []

    def flush_section() -> None:
        nonlocal current
        if current and buffers[current]:
            found[current] = "\n".join(buffers[current]).strip()
        if current:
            buffers[current] = []
        current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        step_match = _NUMBERED_STEP.match(stripped)
        if step_match:
            numbered_steps.append(step_match.group(1).strip())

        if _STEPS_HEADERS.match(stripped):
            flush_section()
            current = "steps_to_reproduce"
            rest = _STEPS_HEADERS.sub("", stripped).strip()
            if rest:
                buffers[current].append(rest)
            continue

        if _EXPECTED_HEADERS.match(stripped):
            flush_section()
            current = "expected_result"
            rest = _EXPECTED_HEADERS.sub("", stripped).strip()
            if rest:
                buffers[current].append(rest)
            continue

        if _ACTUAL_HEADERS.match(stripped):
            flush_section()
            current = "actual_result"
            rest = _ACTUAL_HEADERS.sub("", stripped).strip()
            if rest:
                buffers[current].append(rest)
            continue

        if current:
            buffers[current].append(stripped)

    flush_section()

    if numbered_steps and "steps_to_reproduce" not in found:
        found["steps_to_reproduce"] = "\n".join(
            f"{index}. {step}" for index, step in enumerate(numbered_steps, start=1)
        )

    if "expected_result" not in found or "actual_result" not in found:
        _extract_expected_actual_from_sentences(text, found)

    if "steps_to_reproduce" not in found:
        found["steps_to_reproduce"] = _infer_steps_free_text(text)

    if "expected_result" not in found:
        found["expected_result"] = _infer_expected_free_text(text)

    if "actual_result" not in found:
        found["actual_result"] = _infer_actual_free_text(text)

    found.setdefault("summary", _first_sentence(text))
    return {key: value for key, value in found.items() if value.strip()}


def enrich_draft_from_description(description: str, draft: BugDraft) -> BugDraft:
    """Fill any empty draft fields from the user's description."""
    local = build_local_draft_from_description(description)

    if not draft.summary.strip():
        draft.summary = local.summary

    for field in ("steps_to_reproduce", "expected_result", "actual_result"):
        if not getattr(draft, field, "").strip():
            setattr(draft, field, getattr(local, field, ""))

    if draft.needs_more_info and draft.is_complete():
        draft.needs_more_info = False
        draft.info_request_he = ""

    return draft


def _extract_expected_actual_from_sentences(text: str, found: dict[str, str]) -> None:
    for part in _VS_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if "expected_result" not in found and any(
            token in lower or token in part
            for token in ("מצופה", "אמור", "צריך", "should", "expected")
        ):
            found["expected_result"] = part
        elif "actual_result" not in found and any(
            token in lower or token in part
            for token in ("בפועל", "במקום", "קורה", "actual", "instead")
        ):
            found["actual_result"] = part


def _infer_steps_free_text(text: str) -> str:
    """Infer reproduction steps from keywords — works even for one sentence."""
    sentences = [s.strip() for s in re.split(r"[\.\n]+", text) if s.strip()]
    action_like = [
        sentence
        for sentence in sentences
        if not _EXPECTED_HEADERS.match(sentence)
        and not _ACTUAL_HEADERS.match(sentence)
        and not any(sentence.startswith(p) for p in ("מצופה", "בפועל", "Expected", "Actual"))
    ]
    if len(action_like) >= 2:
        return "\n".join(f"{i}. {s}" for i, s in enumerate(action_like[:5], start=1))

    steps: list[str] = []
    plan_kw = (
        "משימה", "מסלול", "תכנון", "תכנן", "nfz", "אזור אסור", "geofence",
        "mission", "plan", "route", "forbidden", "no-fly", "no fly",
    )
    map_kw = ("מפה", "map", "dtm", "נטען", "נטענת", "load", "loading", "טעינ")
    flight_kw = ("טיסה", "עף", "עפה", "חוצה", "flight", "fly", "cross", "crosses")

    lower = text.lower()
    if any(k in text or k in lower for k in plan_kw):
        steps.append("1. Plan or configure a mission related to the reported issue")
    elif any(k in text or k in lower for k in map_kw):
        steps.append("1. Open the relevant map/screen and perform the reported action")
    else:
        steps.append("1. Perform the operation that triggers the reported behavior")

    if any(k in text or k in lower for k in flight_kw):
        steps.append("2. Start the flight / execute the mission")
        steps.append("3. Observe the drone and system response")
    else:
        steps.append("2. Observe the actual system behavior")

    return "\n".join(steps)


def _infer_expected_free_text(text: str) -> str:
    lower = text.lower()
    if any(k in text or k in lower for k in ("אזור אסור", "nfz", "no-fly", "no fly", "forbidden", "geofence")):
        return (
            "The system should block the mission or prevent the drone from entering "
            "the forbidden zone, or display a clear error before/during the operation."
        )
    if any(k in text or k in lower for k in ("לא נטען", "not load", "not loading", "failed to load", "crash", "קריס")):
        return "The component should load and display correctly without errors."
    if any(k in text or k in lower for k in ("שגיאה", "error", "exception", "timeout")):
        return "The operation should complete successfully without errors."
    return "The system should behave correctly according to standard operation."


def _infer_actual_free_text(text: str) -> str:
    """The user's description describes what actually happens."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    symptom_lines = [
        line
        for line in lines
        if not _STEPS_HEADERS.match(line)
        and not _EXPECTED_HEADERS.match(line)
        and not _ACTUAL_HEADERS.match(line)
        and not _NUMBERED_STEP.match(line)
    ]
    if symptom_lines:
        return " ".join(symptom_lines)
    return text.strip()


def _first_sentence(text: str) -> str:
    parts = re.split(r"[\.\n]", text.strip(), maxsplit=1)
    return parts[0].strip() if parts else text.strip()
