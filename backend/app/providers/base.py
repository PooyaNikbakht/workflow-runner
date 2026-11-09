"""The provider interface every LLM adapter implements."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


class ProviderError(Exception):
    """A provider call failed. `retryable` tells the engine whether a retry could help."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class Task[T: BaseModel]:
    """One structured LLM call: instructions, the input data and the schema of the answer."""

    name: str
    system: str
    instructions: str
    output: type[T]
    context: dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    name: str
    model: str

    async def generate[T: BaseModel](self, task: Task[T]) -> T: ...
