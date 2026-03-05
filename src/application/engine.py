from __future__ import annotations

import time

from application.answer import AnswerService
from application.planner import PlannerService
from application.tool_executor import ToolExecutor
from application.validator import ValidationIssue, ValidatorService
from domain.schemas import EngineAnswer, ToolResponse, UserRequest
from logs import get_logger, write_json_log

logger = get_logger("Engine")


class LedgerMindEngine:
    def __init__(
        self,
        planner: PlannerService,
        tool_executor: ToolExecutor,
        answer_service: AnswerService,
        validator: ValidatorService,
    ):
        self._planner = planner
        self._tool_executor = tool_executor
        self._answer_service = answer_service
        self._validator = validator

    def run(self, request: UserRequest) -> tuple[EngineAnswer, list[ValidationIssue]]:
        logger.info("Engine run start request_id=%s user_id=%s", request.request_id, request.user_id)
        t0 = time.perf_counter()

        t = time.perf_counter()
        plan = self._planner.plan(request)
        logger.info("Planner complete in %.2fs calls=%d", time.perf_counter() - t, len(plan.calls))

        t = time.perf_counter()
        evidence = self._tool_executor.run_calls(plan, request)
        logger.info("Tool execution complete in %.2fs responses=%d", time.perf_counter() - t, len(evidence))
        self._dump_evidence_snapshot(request, plan.model_dump(by_alias=True), evidence)

        t = time.perf_counter()
        answer = self._answer_service.compose(request, plan, evidence)
        logger.info("Answer generation complete in %.2fs", time.perf_counter() - t)

        t = time.perf_counter()
        issues = self._validator.validate(answer, evidence)
        logger.info("Validation complete in %.2fs issues=%d", time.perf_counter() - t, len(issues))

        logger.info("Engine run complete in %.2fs", time.perf_counter() - t0)
        return answer, issues

    def _dump_evidence_snapshot(self, request: UserRequest, plan_payload: dict, evidence: list[ToolResponse]) -> None:
        payload = {
            "request": request.model_dump(mode="json"),
            "plan": plan_payload,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }
        output_path = write_json_log(
            name="Engine",
            message="evidence_snapshot",
            payload=payload,
            request_id=request.request_id,
        )
        if output_path is not None:
            logger.info("Engine evidence snapshot written path=%s entries=%d", output_path, len(evidence))
