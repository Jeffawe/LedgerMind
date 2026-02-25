from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from domain.schemas import EngineAnswer, ToolResponse


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str = ""
    severity: str = "error"  # "error" | "warn"


class ValidatorService:
    """
    Deterministic validator for EngineAnswer.

    MVP goals:
      - Output schema checks
      - Grounding checks (citations exist; optional path resolution)
      - Basic content constraints (options count, required fields)
      - Heuristic: detect uncited numeric claims in free-text
    """

    EXPECTED_SCHEMA = "ledgermind.answer.v1"
    MIN_OPTIONS = 2
    MAX_OPTIONS = 3

    # Simple numeric detection: 1,234.56 or 123.45 or 123
    _NUM_RE = re.compile(r"(?<![\w/])(\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\$?\d+(?:\.\d+)?)(?![\w/])")

    def validate(self, answer: EngineAnswer, evidence: list[ToolResponse]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        evidence_bundle = self._normalize_evidence(evidence)

        # --- 1) Schema/version checks ---
        if answer.schema_version != self.EXPECTED_SCHEMA:
            issues.append(ValidationIssue(
                code="SCHEMA_VERSION",
                message=f"Unexpected answer schema version: {answer.schema_version!r}",
                path="schema_version",
            ))

        # --- 2) Required content checks ---
        if not getattr(answer.summary, "headline", ""):
            issues.append(ValidationIssue(
                code="MISSING_HEADLINE",
                message="Missing summary headline",
                path="summary.headline",
            ))

        if answer.recommended_action is None or not getattr(answer.recommended_action, "title", ""):
            issues.append(ValidationIssue(
                code="MISSING_RECOMMENDED_ACTION_TITLE",
                message="Missing recommended action title",
                path="recommended_action.title",
            ))

        # --- 3) Options constraints ---
        options = getattr(answer, "options", []) or []
        if not (self.MIN_OPTIONS <= len(options) <= self.MAX_OPTIONS):
            issues.append(ValidationIssue(
                code="OPTIONS_COUNT",
                message=f"Expected {self.MIN_OPTIONS}-{self.MAX_OPTIONS} options; got {len(options)}",
                path="options",
                severity="warn",
            ))

        # Ensure each option has minimal fields (adapt field names to your schema)
        for i, opt in enumerate(options):
            if not getattr(opt, "title", ""):
                issues.append(ValidationIssue(
                    code="OPTION_MISSING_TITLE",
                    message=f"Option {i} missing title",
                    path=f"options[{i}].title",
                ))
            steps = getattr(opt, "steps", None)
            if steps is None or len(steps) == 0:
                issues.append(ValidationIssue(
                    code="OPTION_MISSING_STEPS",
                    message=f"Option {i} has no steps",
                    path=f"options[{i}].steps",
                    severity="warn",
                ))

        # --- 4) Evidence grounding checks ---
        # Expect evidence to include a citations map, OR raw tool outputs with citation lists.
        known_citation_ids = self._collect_citation_ids(evidence_bundle)

        supporting_numbers = getattr(answer, "supporting_numbers", []) or []
        for idx, number in enumerate(supporting_numbers):
            ntype = getattr(number, "type", None)
            nid = getattr(number, "id", f"supporting_numbers[{idx}]")

            if ntype == "evidence":
                ref = getattr(number, "evidence_ref", None)
                if not ref:
                    issues.append(ValidationIssue(
                        code="EVIDENCE_MISSING_REF",
                        message=f"Evidence number missing evidence_ref: {nid}",
                        path=f"supporting_numbers[{idx}].evidence_ref",
                    ))
                    continue

                citation_id = getattr(ref, "citation_id", None)
                if not citation_id:
                    issues.append(ValidationIssue(
                        code="EVIDENCE_MISSING_CITATION_ID",
                        message=f"Evidence ref missing citation_id: {nid}",
                        path=f"supporting_numbers[{idx}].evidence_ref.citation_id",
                    ))
                    continue

                if citation_id not in known_citation_ids:
                    issues.append(ValidationIssue(
                        code="UNKNOWN_CITATION_ID",
                        message=f"citation_id {citation_id!r} not found in evidence bundle (number {nid})",
                        path=f"supporting_numbers[{idx}].evidence_ref.citation_id",
                    ))
                    continue

                # Optional: try to resolve evidence_ref.path
                path = getattr(ref, "path", None)
                if path:
                    ok = self._try_resolve_path(evidence_bundle, citation_id=citation_id, path=path)
                    if not ok:
                        issues.append(ValidationIssue(
                            code="EVIDENCE_PATH_UNRESOLVED",
                            message=f"Could not resolve evidence path {path!r} for citation {citation_id!r} (number {nid})",
                            path=f"supporting_numbers[{idx}].evidence_ref.path",
                            severity="warn",
                        ))

            elif ntype == "assumption":
                if not getattr(number, "assumption", ""):
                    issues.append(ValidationIssue(
                        code="ASSUMPTION_MISSING_RATIONALE",
                        message=f"Assumption number missing rationale: {nid}",
                        path=f"supporting_numbers[{idx}].assumption",
                    ))
            else:
                issues.append(ValidationIssue(
                    code="UNKNOWN_NUMBER_TYPE",
                    message=f"Unknown supporting_numbers[{idx}].type: {ntype!r}",
                    path=f"supporting_numbers[{idx}].type",
                ))

        # --- 5) Heuristic: numeric claims in text must be backed by supporting_numbers ---
        # MVP heuristic:
        #  - Collect all numeric tokens present in supporting_numbers values
        #  - Flag numbers found in headline/bullets/recommendation text that don't appear there
        supported_numeric_tokens = self._supported_number_tokens(answer)

        text_fields = self._gather_text_fields(answer)
        for path, text in text_fields:
            for token in self._extract_numeric_tokens(text):
                # Skip low-signal single-digit integers (e.g., "1", "4 weeks") to reduce noise.
                if re.fullmatch(r"\$?\d", token):
                    continue
                if token not in supported_numeric_tokens:
                    issues.append(ValidationIssue(
                        code="UNCITED_NUMBER_IN_TEXT",
                        message=f"Found numeric token {token!r} in {path} not present in supporting_numbers",
                        path=path,
                        severity="warn",
                    ))

        return issues

    # ---------------- helpers ----------------

    def _normalize_evidence(self, evidence: list[ToolResponse] | dict[str, Any]) -> dict[str, Any]:
        """
        Normalize current runtime evidence (list[ToolResponse]) into a dict bundle shape
        the grounding checks can consume. Keeps compatibility with future explicit bundles.
        """
        if isinstance(evidence, dict):
            return evidence

        tool_outputs: dict[str, dict[str, Any]] = {}
        citations: dict[str, dict[str, Any]] = {}

        for idx, item in enumerate(evidence, start=1):
            tool_outputs[item.tool] = {
                "request_id": item.request_id,
                "ok": item.ok,
                "result": item.result,
                "errors": item.errors,
                "context": item.context.model_dump(),
            }
            # Synthetic citation entry so current answer fallback refs like c1 resolve.
            citations[f"c{idx}"] = {"result": item.result}

        return {"tool_outputs": tool_outputs, "citations": citations}

    def _collect_citation_ids(self, evidence: dict[str, Any]) -> set[str]:
        """
        Supports evidence formats like:
          evidence = {
            "citations": {"c1": {...}, "c2": {...}},
            "tool_outputs": {...}
          }
        or evidence = {"c1": {...}, "c2": {...}}
        """
        # Preferred: explicit citations map
        citations = evidence.get("citations")
        if isinstance(citations, dict):
            return set(citations.keys())

        # Fallback: scan tool outputs for lists of citations
        ids: set[str] = set()
        tool_outputs = evidence.get("tool_outputs")
        if isinstance(tool_outputs, dict):
            for _, out in tool_outputs.items():
                for c in (out.get("citations") or []):
                    cid = c.get("citation_id")
                    if cid:
                        ids.add(cid)

        # Last fallback: if evidence itself looks like citations map
        for k, v in evidence.items():
            if isinstance(v, dict) and k.startswith("c"):
                ids.add(k)

        return ids

    def _try_resolve_path(self, evidence: dict[str, Any], citation_id: str, path: str) -> bool:
        """
        Optional best-effort resolver.

        This is intentionally conservative; path syntax is your choice.
        For MVP, you can treat any path resolution failure as WARN, not ERROR.
        """
        citations = evidence.get("citations")
        if not isinstance(citations, dict):
            return True  # can't verify, don't fail MVP

        payload = citations.get(citation_id)
        if not isinstance(payload, dict):
            return False

        # Very simple dotted-path resolver (no filters like [category=Groceries])
        cur: Any = payload
        for part in path.split("."):
            if not part:
                continue
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return False
        return True

    def _supported_number_tokens(self, answer: EngineAnswer) -> set[str]:
        """
        Normalize supporting numbers into common textual forms to reduce false positives.
        Example: 487.45 -> {"487.45", "487", "$487.45", "$487"}
        """
        tokens: set[str] = set()
        for n in (getattr(answer, "supporting_numbers", []) or []):
            val = getattr(n, "value", None)
            unit = getattr(n, "unit", "")
            if val is None:
                continue

            # Convert to a few canonical string forms
            s = str(val)
            tokens.add(s)

            # Add integer form if it looks like a float
            try:
                f = float(val)
                i = str(int(round(f)))
                tokens.add(i)
                tokens.add(f"${s}")
                tokens.add(f"${i}")
            except Exception:
                pass

            # If unit is USD, allow $ prefix
            if unit == "USD":
                tokens.add(f"${s}")

        return tokens

    def _gather_text_fields(self, answer: EngineAnswer) -> list[tuple[str, str]]:
        """
        Collect the free-text fields where numeric hallucinations tend to happen.
        Adjust these to match your EngineAnswer model.
        """
        fields: list[tuple[str, str]] = []

        summary = getattr(answer, "summary", None)
        if summary:
            headline = getattr(summary, "headline", "")
            if headline:
                fields.append(("summary.headline", headline))
            bullets = getattr(summary, "bullets", None) or []
            for i, b in enumerate(bullets):
                if b:
                    fields.append((f"summary.bullets[{i}]", b))

        rec = getattr(answer, "recommended_action", None)
        if rec:
            title = getattr(rec, "title", "")
            if title:
                fields.append(("recommended_action.title", title))
            for i, s in enumerate(getattr(rec, "next_7_days", None) or []):
                fields.append((f"recommended_action.next_7_days[{i}]", s))
            for i, s in enumerate(getattr(rec, "next_30_days", None) or []):
                fields.append((f"recommended_action.next_30_days[{i}]", s))

        for i, r in enumerate(getattr(answer, "risks_and_tradeoffs", None) or []):
            fields.append((f"risks_and_tradeoffs[{i}]", r))

        return fields

    def _extract_numeric_tokens(self, text: str) -> Iterable[str]:
        if not text:
            return []
        # Returns matched numeric strings (e.g., "$487.45", "487.45", "1,200")
        return [m.group(1) for m in self._NUM_RE.finditer(text)]
