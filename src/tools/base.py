from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from domain.schemas import ToolRequest, ToolResponse, TransactionQuery
from pydantic import ValidationError


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, Any]


class Tool(ABC):
    name: str
    description: str = ""

    @abstractmethod
    def run(self, request: ToolRequest) -> ToolResponse:
        raise NotImplementedError

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, args_schema={})
