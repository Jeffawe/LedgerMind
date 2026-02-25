from __future__ import annotations

import logging
import time

from application.answer import AnswerService
from application.planner import PlannerService
from application.tool_executor import ToolExecutor
from application.validator import ValidationIssue, ValidatorService
from domain.schemas import EngineAnswer, UserRequest

logger = logging.getLogger(__name__)


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

        t = time.perf_counter()
        answer = self._answer_service.compose(request, plan, evidence)
        logger.info("Answer generation complete in %.2fs", time.perf_counter() - t)

        t = time.perf_counter()
        issues = self._validator.validate(answer, evidence)
        logger.info("Validation complete in %.2fs issues=%d", time.perf_counter() - t, len(issues))

        logger.info("Engine run complete in %.2fs", time.perf_counter() - t0)
        return answer, issues
