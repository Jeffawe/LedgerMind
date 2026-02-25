from __future__ import annotations

import logging
import time

from domain.schemas import LedgerMindPlan, ToolContext, ToolRequest, ToolResponse, UserRequest
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def run_calls(self, plan: LedgerMindPlan, user_request: UserRequest) -> list[ToolResponse]:
        context = ToolContext(
            user_id=user_request.user_id,
            ledger_id="ldg_main",
            timezone=user_request.context.timezone,
            policy_profile=user_request.context.policy_profile,
        )
        responses: list[ToolResponse] = []
        for call in plan.calls:
            req = ToolRequest(
                request_id=f"{user_request.request_id}:{call.id}",
                tool=call.tool,
                args=call.args,
                context=context,
            )
            logger.info("ToolExecutor running call_id=%s tool=%s", call.id, call.tool)
            t = time.perf_counter()
            try:
                tool = self._registry.get_tool(req.tool)
                response = tool.run(req)
            except Exception as exc:
                logger.exception("ToolExecutor failed call_id=%s tool=%s", call.id, call.tool)
                response = ToolResponse(
                    request_id=req.request_id,
                    tool=req.tool,
                    ok=False,
                    errors=[str(exc) or exc.__class__.__name__],
                    context=context,
                )
            responses.append(response)
            logger.info("ToolExecutor finished call_id=%s tool=%s in %.2fs ok=%s", call.id, call.tool, time.perf_counter() - t, response.ok)
        return responses
