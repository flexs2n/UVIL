"""BEq statement-equivalence probe (R4): kernel-checked statement faithfulness.

Proves `(statement) ↔ (sequent-encoding)` by `omega` - decidable on the LIA
slice (the ITPEval BEq generalization to linear arithmetic). The interface
accepts **any** statement text: M3's statements are generated from the same
Term (so the probe passes by construction and validates the plumbing), but
hand-written or LLM-translated statements get the identical guard later.

Outcome mapping (fail loud, never silently upgrade):
- kernel-accepted biconditional -> I9 `Translation` with
  `soundness_discipline="kernel-checked"` (source kind `obligation`, target
  kind `lean4-statement`) - the statement-faithfulness evidence that upgrades
  G1 to G2 in `record_lean`;
- omega rejection or unsupported term -> `"lossy"` with the divergent
  statement (and reason) in `residuals.dropped_fragments` - G2 withheld.

Discovery pins (leanprover/lean4:v4.33.1):
- `↔` between linear Int props discharges, including hypothesis chains -
  but ONLY with the binders hoisted into theorem parameters: a parenthesized
  `∀`-prefixed statement (`(∀ x, P) ↔ (∀ x, P)`) is INVISIBLE to omega
  ("no usable constraints found"). The probe therefore strips the leading
  `∀ (n : S) ...` binder prefix and hoists it into the theorem's parameter
  list; statements that do not share the sequent's binders fail to compile
  and come back `lossy` (honest).
- `↔` between pure Bool atoms does NOT discharge - those probes come back
  lossy, honestly.
"""

from __future__ import annotations

import hashlib
import re

from ...artifacts import Obligation, Translation, artifact_id, sha256_hex
from ...artifacts.translation import Residuals
from .backend import LeanBackend
from .encode import TARGET_KIND, UnsupportedTermError, lean_statement

BEQ_TARGET_KIND = "lean4-statement"

_FORALL_PREFIX = re.compile(r"^∀\s*(?P<binders>(?:\([^()]+\)\s*)+),(?P<body>.*)$", re.DOTALL)


def beq_theorem_name(goal: Obligation, statement: str) -> str:
    """Stable probe name over (obligation, statement) - different statements
    for the same obligation get different probes."""
    payload = artifact_id(goal).encode("utf-8") + statement.encode("utf-8")
    return "uvil_beq_" + hashlib.sha256(payload).hexdigest()[:12]


def _split_binders(statement: str) -> tuple[str, str] | None:
    """Split a `∀ (n : S) ..., body` statement into (binder_groups, body).
    Returns None when there is no leading forall (the common ∀-free case)."""
    match = _FORALL_PREFIX.match(statement.strip())
    if match is None:
        return None
    return match.group("binders").strip(), match.group("body").strip()


def _probe_text(name: str, statement: str, sequent: str) -> str:
    """Build the biconditional probe with binders hoisted into theorem
    parameters (discovery: parenthesized forall bodies are omega-invisible)."""
    stmt_split = _split_binders(statement)
    seq_split = _split_binders(sequent)
    # the sequent's binders are authoritative: the statement must typecheck
    # under them, else the probe compile-fails and comes back lossy
    binders, seq_body = seq_split if seq_split is not None else ("", sequent)
    stmt_body = stmt_split[1] if stmt_split is not None else statement
    params = f" {binders}" if binders else ""
    return f"theorem {name}{params} : ({stmt_body}) ↔ ({seq_body}) := by omega"


def statement_equivalence(
    goal: Obligation,
    statement: str,
    backend: LeanBackend | None = None,
) -> Translation:
    """Probe whether `statement` is a faithful Lean rendering of `goal`'s
    sequent: emit `(statement) ↔ (sequent-encoding)` and let the pinned
    kernel decide. Returns an I9 `Translation`; never raises for a rejected
    statement (that is a `lossy` outcome, not an error)."""
    source_aid = artifact_id(goal)
    target_ref = f"{BEQ_TARGET_KIND}:{sha256_hex(statement.encode('utf-8'))}"
    base = Translation(
        source_artifact=source_aid,
        target_artifact=target_ref,
        source_kind="obligation",
        target_kind=BEQ_TARGET_KIND,
        soundness_discipline="lossy",
        notes=None,
    )

    def lossy(reason: str) -> Translation:
        return base.model_copy(
            update={
                "soundness_discipline": "lossy",
                "residuals": Residuals(dropped_fragments=[reason, statement]),
                "notes": (
                    "BEq statement-equivalence probe: statement not faithful to the obligation"
                ),
            }
        )

    try:
        sequent = lean_statement(goal)
    except UnsupportedTermError as e:
        return lossy(f"obligation has no Lean encoding: {e.native_message}")

    probe = _probe_text(beq_theorem_name(goal, statement), statement, sequent)
    if backend is None:
        try:
            backend = LeanBackend()
        except Exception as e:  # LeanNotInstalled / LeanVersionMismatch
            return lossy(f"probe could not run (backend unavailable): {e}")

    (verdict,) = backend.check_batch([probe])
    if verdict.status != "attested":
        return lossy(
            f"the pinned kernel rejected the biconditional probe "
            f"(status={verdict.status}):\n{verdict.native_output or ''}"
        )

    return base.model_copy(
        update={
            "soundness_discipline": "kernel-checked",
            "residuals": Residuals(),
            "notes": (
                "BEq statement-equivalence probe: the pinned Lean kernel "
                f"accepted (statement) ↔ (sequent) by omega ({TARGET_KIND})"
            ),
        }
    )
