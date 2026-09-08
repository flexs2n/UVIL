"""Shared builders for artifact fixtures used across tests and examples."""

from __future__ import annotations

from uvil.artifacts import (
    Counterexample,
    Diagnostic,
    Intent,
    Obligation,
    Program,
    Proof,
    Run,
    Specification,
    Translation,
)
from uvil.artifacts.counterexample import BackendWitness, SharedRender, TraceState
from uvil.artifacts.diagnostic import DiagnosticKind, Loc
from uvil.artifacts.obligation import Sequent
from uvil.artifacts.terms import (
    Term,
    const,
    t_and,
    t_eq,
    t_ge,
    t_le,
    t_lt,
    t_sub,
    var,
)

COUNTEREXAMPLE_REF = "obl:x"


def make_intent() -> Intent:
    return Intent(
        title="Vector capacity invariant",
        requirements=[
            "A push never exceeds the declared capacity of the vector.",
            "Length is always bounded by capacity.",
        ],
        constraints=["amortized O(1) push"],
        forbidden_behaviors=["out-of-bounds write"],
    )


def make_spec() -> Specification:
    return Specification(
        intent_ref=None,
        profile="uvil.verus@1",
        theories=["uvil.core.int@1", "uvil.core.seq@1"],
        semantics_model="model:why3-memory.v1",
        subject="collections.vec.push",
        contracts={
            "requires": [t_le(var("len"), var("cap"))],
            "ensures": [t_and(t_le(var("len'"), var("cap")), t_ge(var("len'"), const(0)))],
            "modifies": ["heap"],
        },
        shadows=[
            {
                "name": "cap-nonneg-counter",
                "formula": {"op": "lt", "args": [var("cap"), const(0)]},
                "expect": "refute",
            }
        ],
    )


def make_program() -> Program:
    return Program(
        language="rust",
        source_ref="src/collections/vec.rs#push",
        symbol="push",
        fragment="fn push(&mut self, v: T) { self.buf[self.len] = v; self.len += 1; }",
        semantics_model="model:why3-memory.v1",
    )


def make_obligation() -> Obligation:
    return Obligation(
        spec_ref="spec:collections vec push requires capacity",
        program_ref="prog:collections vec push",
        semantics_model="model:why3-memory.v1",
        sequent={
            "context": [
                {
                    "op": "ge",
                    "args": [{"op": "var", "args": ["cap"]}, {"op": "const", "args": [0]}],
                },
                {
                    "op": "le",
                    "args": [{"op": "var", "args": ["len"]}, {"op": "var", "args": ["cap"]}],
                },
                {
                    "op": "lt",
                    "args": [{"op": "var", "args": ["len"]}, {"op": "var", "args": ["cap"]}],
                },
            ],
            "goal": {
                "op": "le",
                "args": [
                    {
                        "op": "add",
                        "args": [{"op": "var", "args": ["len"]}, {"op": "const", "args": [1]}],
                    },
                    {"op": "var", "args": ["cap"]},
                ],
            },
        },
        theories=["uvil.core.int@1"],
        target_profile="uvil.verus@1",
        status="open",
        cost_budget={"solver_ms": 2000, "kernel_ms": 500},
    )


def make_proof(obligation_ref: str) -> Proof:
    return Proof(
        obligation_ref=obligation_ref,
        backend={"name": "z3", "version": "4.13.0", "kernel_hash": "sha256:deadbeef"},
        payload={"format": "smt-certificate-alethe", "inline": "(proof ...)"},
        checker={"entry": "uvil-check smt", "independent": True},
    )


def make_counterexample(obligation_ref: str) -> Counterexample:
    return Counterexample(
        obligation_ref=obligation_ref,
        kind="valuation",
        valuation={"len": const(3), "cap": const(2)},
        shared_render={"smt_lib_valuation": "((len 3) (cap 2))", "human_summary": "len=3 > cap=2"},
    )


def make_trace_counterexample(obligation_ref: str) -> Counterexample:
    return Counterexample(
        obligation_ref=obligation_ref,
        kind="trace",
        trace=[
            TraceState(vars={"x": "0", "pc": "entry"}, loc="init"),
            TraceState(vars={"x": "1", "pc": "loop.head"}),
            TraceState(vars={"x": "2", "pc": "exit"}, loc="done"),
        ],
        shared_render=SharedRender(
            human_summary="[unverified human rendering]\ntrace with 3 steps"
        ),
        backend_witness=BackendWitness(format="esbmc-trace", payload=None),
    )


def make_scenario_counterexample(obligation_ref: str) -> Counterexample:
    return Counterexample(
        obligation_ref=obligation_ref,
        kind="scenario",
        scenario=[
            TraceState(vars={"balance": "100", "state": "idle"}, loc="Init"),
            TraceState(vars={"balance": "60", "state": "withdrawn"}, loc="Next"),
        ],
        shared_render=SharedRender(
            human_summary="[unverified human rendering]\nscenario with 2 states"
        ),
        backend_witness=BackendWitness(format="tlc-scenario", payload=None),
    )


def make_counterspec_counterexample(obligation_ref: str) -> Counterexample:
    return Counterexample(
        obligation_ref=obligation_ref,
        kind="counterspec",
        counter_spec=t_lt(var("cap"), const(0)),
        shared_render=SharedRender(
            human_summary=(
                "[unverified human rendering]\nshadow probe: the spec forces the "
                "counter-hypothesis (vacuous)"
            )
        ),
        backend_witness=BackendWitness(format="shadow-probe", payload=None),
    )


def make_diagnostic(obligation_ref: str) -> Diagnostic:
    return Diagnostic(
        obligation_ref=obligation_ref,
        kind="unproved",
        loc={"file": "src/collections/vec.rs", "line": 87, "symbol": "push"},
        native_message="failed to prove: len + 1 <= cap",
        llm_explanation={"text": "likely missing cap increment before write", "unverified": True},
    )


_DIAGNOSTIC_MESSAGES: dict[str, str] = {
    "unproved": "failed to prove: x + x == 3 * x",
    "vacuous": "shadow probe: spec context forces the counter-hypothesis (vacuous)",
    "timeout": "backend z3 returned timeout within budget 300ms",
    "parse": "unexpected token ';'\n  assert x > 0;;",
    "semantic-mismatch": "spec feature unsupported by target profile uvil.core@1",
    "unknown": "backend z3 returned unknown within budget 1000ms",
}


def make_diagnostic_of_kind(
    kind: DiagnosticKind, obligation_ref: str | None = COUNTEREXAMPLE_REF
) -> Diagnostic:
    """Representative I7 builder for every diagnostic kind (renderer fixtures)."""
    return Diagnostic(
        obligation_ref=obligation_ref,
        kind=kind,
        loc=Loc(file="examples/vec_push/vec_push.bpl", line=3, symbol="p"),
        native_message=_DIAGNOSTIC_MESSAGES[kind],
        llm_explanation=(
            {"text": "the asserted constant looks wrong for all inputs", "unverified": True}
            if kind == "unproved"
            else None
        ),
    )


def make_run(verdict_refs: list[str]) -> Run:
    return Run(
        tool={"name": "z3", "version": "4.13.0", "flags": ["smt.random_seed=0"]},
        verdicts=[
            {"obligation_ref": ref, "status": "discharged", "time_ms": 42} for ref in verdict_refs
        ],
        resource_stats={"wall_ms": 420, "max_memory_mb": 128},
        kernel_attestations=[{"backend": "z3", "kernel_hash": "sha256:deadbeef", "checked": True}],
    )


def make_translation(source: str, target: str) -> Translation:
    return Translation(
        source_artifact=source,
        target_artifact=target,
        source_kind="obligation",
        target_kind="smt-assertion",
        mapping=[{"source": "sequent.goal", "target": "assert.0"}],
        soundness_discipline="roundtrip-validated",
        residuals={"assumptions_added": [], "dropped_fragments": [], "residual_obligations": []},
    )


def vec_goal_term() -> Term:
    return t_eq(t_sub(var("cap"), var("len")), const(0))


__all__ = [
    "COUNTEREXAMPLE_REF",
    "Sequent",
    "make_counterexample",
    "make_counterspec_counterexample",
    "make_diagnostic",
    "make_diagnostic_of_kind",
    "make_intent",
    "make_obligation",
    "make_program",
    "make_proof",
    "make_run",
    "make_scenario_counterexample",
    "make_spec",
    "make_trace_counterexample",
    "make_translation",
    "vec_goal_term",
]
