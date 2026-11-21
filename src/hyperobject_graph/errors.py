"""The one exception the core raises, and the problem record its validator returns."""

from __future__ import annotations

from dataclasses import dataclass


class GraphCoreError(ValueError):
    """A graph document, a declaration or a node pack broke the core contract.

    ``code`` names the rule (``"cycle"``, ``"socket-type"``, ``"dangling-ref"``,
    ``"unbound-input"``, ``"script-node"`` ...) so a caller can count or filter
    without parsing the message.
    """

    def __init__(self, message: str, *, code: str = "graph"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a document. ``where`` is a JSON-pointer-like path."""

    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message} [{self.code}]"
