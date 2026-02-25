from __future__ import annotations

from datetime import datetime

from application.answer import AnswerService
from application.engine import LedgerMindEngine
from application.planner import PlannerService
from application.tool_executor import ToolExecutor
from application.validator import ValidatorService
from domain.schemas import UserRequest, UserRequestContext
from tools.registry import registry


def build_engine() -> LedgerMindEngine:
    import tools  # noqa: F401

    return LedgerMindEngine(
        planner=PlannerService(registry=registry),
        tool_executor=ToolExecutor(registry),
        answer_service=AnswerService(),
        validator=ValidatorService(),
    )

def main() -> None:
    message = input("LedgerMind > ").strip()
    if not message:
        message = "Show me this month's spending overview"

    request = UserRequest(
        request_id=f"req_cli_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        user_id="u_cli",
        message=message,
        context=UserRequestContext(timezone="America/New_York", policy_profile="default_v1"),
    )
    engine = build_engine()
    answer, issues = engine.run(request)
    print(answer.model_dump_json(indent=2, by_alias=True))
    if issues:
        print({"issues": [issue.__dict__ for issue in issues]})


if __name__ == "__main__":
    main()
