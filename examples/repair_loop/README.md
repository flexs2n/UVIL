# Repair-loop harness example

The M2 exit-criterion demo: **one repair consumer handles failures from ≥2
backends through the same interface with no backend-specific prompting.**

## Agent interface contract

```python
class RepairAgent(Protocol):
    def repair(self, source: str, feedback: dict) -> str | None: ...
```

The agent receives the current Boogie source text and a feedback dict, and
returns the repaired source, or `None` to give up. The harness
(`harness.py:run_loop`) drives:

    import -> parse diagnostics? feed back
            : no obligations left? success (claim de-scoped)
            : check -> all discharged? success
            : feed back -> agent repairs -> repeat (budget: max_iterations)

## Feedback schema (common JSON form)

```json
{
  "diagnostics":    [ "<I7 common-JSON>", ... ],
  "counterexamples": [ "<I6 common-JSON>", ... ]
}
```

- I7 common-JSON: `{uvil_type, kind, obligation_ref, loc, native_message,
  llm_explanation}` - kinds `unproved | vacuous | timeout | parse |
  semantic-mismatch | unknown`.
- I6 common-JSON: `{uvil_type, kind, obligation_ref, backend_witness, ...}` -
  kinds `valuation | trace | scenario | counterspec`; terms are term JSON.
  This is `uvil.render.to_common_json` output; there are **no backend fields**
  beyond what the artifacts already carry.

A `native` feedback form (`harness.run_loop(..., feedback_form="native")`)
exists only for the experiment's native arm: it hands the agent raw backend
text (verbatim z3 model sexprs / raw parser error lines) - the bespoke
per-backend path the standardized interface replaces.

## Measurement protocol

`experiment.py` runs two arms over the failure corpus subset the stubs target
(deterministic, no LLM/network):

1. **standardized** - one `StubRepairer` object fed common JSON, repairing z3
   refutations *and* Boogie-parser failures unchanged.
2. **native** - bespoke per-backend agents (`NativeZ3Repairer` regex-parses
   raw z3 model sexprs; `NativeBoogieRepairer` re-derives locations from raw
   parser error text), selected by per-backend dispatch.

It reports per-arm success counts and lines of backend-specific agent code;
numbers land in `RESULTS.md` (committed - the stubs are deterministic, so the
results reproduce exactly).

**Honesty caveat:** the stubs *de-scope* claims to `assume` form for the
parse families and target the wrong-constant refutation family for the
valuation witness. The measured claim is interface uniformity (one agent,
≥2 backends), not repair power.

## Plugging a real agent

Implement `RepairAgent.repair` with any LLM/tool backend and call
`run_loop(source, your_agent, max_iterations=..., backend=...)`. The harness
never changes: it feeds the same common-JSON feedback regardless of backend
(`--backend z3|cvc5` upstream), so no backend-specific prompting belongs in
the agent. Keep `llm_explanation` consumption unverified-only: downstream
tools must never treat it as a guarantee.
