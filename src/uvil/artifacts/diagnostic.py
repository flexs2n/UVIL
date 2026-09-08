"""I7 - Failure Diagnostic: location, kind, verbatim backend message, LLM slot.

Kinds: {unproved, vacuous, timeout, parse, semantic-mismatch, unknown} - aligned
with Strata's VerificationModes taxonomy. The backend-native message is preserved
verbatim for round-tripping. The `intent-level slot` for LLM explanations is
permanently marked unverified: agents may consume it; downstream tools must never
treat it as a guarantee.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import Artifact

DiagnosticKind = Literal["unproved", "vacuous", "timeout", "parse", "semantic-mismatch", "unknown"]


class Loc(BaseModel):
    file: str | None = None
    line: int | None = None
    col: int | None = None
    symbol: str | None = None


class LlmExplanation(BaseModel):
    text: str
    unverified: Literal[True] = True


class Diagnostic(Artifact):
    uvil_type = "diagnostic"

    obligation_ref: str | None = None
    run_ref: str | None = None
    kind: DiagnosticKind
    loc: Loc = Field(default_factory=Loc)
    native_message: str
    llm_explanation: LlmExplanation | None = None
