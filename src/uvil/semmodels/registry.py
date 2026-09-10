"""Semantics-model registry.

Semantics models are the versioned, citable mappings from source constructs into
the shared theories (Why3-style memory model, Aeneas-style functional translation,
ESBMC GOTO/SSA, …). Making them first-class hashable objects is what turns
"library mismatch" into explicit context instead of silent assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticsModelEntry:
    model_id: str  # e.g. "model:why3-memory.v1"
    name: str
    version: str
    description: str
    theories: tuple[str, ...] = ()
    profiles: tuple[str, ...] = field(default=())
    citation: str | None = None

    def __post_init__(self) -> None:
        if not self.model_id.startswith("model:"):
            raise ValueError(f"model_id must start with 'model:', got {self.model_id!r}")


WHY3_MEMORY_V1 = SemanticsModelEntry(
    model_id="model:why3-memory.v1",
    name="why3-memory",
    version="v1",
    description=(
        "Why3-style typed memory model (M1 refinement): program variables are "
        "separate from a mutable heap store keyed by references; Boogie-style "
        "arrays/maps `[T1,..,Tn]T` map to `uvil.core.array` (`select`/`store`), "
        "sequence types `seq<T>` map to `uvil.core.seq` (`seq.len`/`seq.nth`/…), "
        "and scalar globals live directly in the store with no aliasing between "
        "untracked references. Covers the array/heap operations the M1 corpus "
        "actually exercises; deeper heap frames and region separation stay out "
        "of scope until a later model version."
    ),
    theories=(
        "uvil.core.int@1",
        "uvil.core.bool@1",
        "uvil.core.real@1",
        "uvil.core.array@1",
        "uvil.core.seq@1",
    ),
    profiles=("uvil.boogie@1",),
    citation="Bobot, Filliâtre, Marché, Paskevich. Why3. VSTTE 2011.",
)


ESBMC_GOTO_V1 = SemanticsModelEntry(
    model_id="model:esbmc-goto.v1",
    name="esbmc-goto",
    version="v1",
    description=(
        "ESBMC GOTO/SSA harness model (M4): C verification harnesses checked "
        "by the pinned ESBMC binary against real C semantics (32-bit two's "
        "complement, its GOTO conversion, and its internal property checks for "
        "overflow/division-by-zero/array-bounds/pointer misuse). Import-side "
        "obligations use the documented bounded-integer harness abstraction "
        "(uvil.adapters.esbmc.import_c): unbounded-Int/Euclidean div-mod "
        "sequents over uvil.core.int@1 - C wraparound and ESBMC-internal "
        "properties are intentionally NOT modeled in the sequents, which is "
        "why model-checking verdicts never upgrade them (fail-loud R1)."
    ),
    theories=(
        "uvil.core.int@1",
        "uvil.core.bool@1",
    ),
    profiles=("uvil.esbmc-c@1",),
    citation="Cordeiro, Fischer. ESBMC 2.0: Scalable Verilog/C Bounded Model Checking. TACAS 2014.",
)


STRATA_CORE_V1 = SemanticsModelEntry(
    model_id="model:strata-core.v1",
    name="strata-core",
    version="v1",
    description=(
        "Strata Core dialect model (M4): Strata (github.com/strata-org/Strata) "
        "unifies verification dialects toward a vendor Lean core. UVIL consumes "
        "its artifacts as a FRONTEND, not a neutral peer - Strata's VC "
        "generation is not UVIL's TCB (vendor-TCB caveat, recorded on every "
        "imported artifact). Guarantees come only from UVIL's own backends "
        "re-dispatching the shared-subset VCs; vendor verdicts are recorded as "
        "opaque I5 payloads with checker.independent=False."
    ),
    theories=(
        "uvil.core.int@1",
        "uvil.core.bool@1",
    ),
    profiles=("uvil.strata-core@1",),
    citation="Strata: layered verification dialects (Strata contributors, github.com/strata-org).",
)


AENEAS_FUNCTIONAL_V1 = SemanticsModelEntry(
    model_id="model:aeneas-functional.v1",
    name="aeneas-functional",
    version="v1",
    description=(
        "Aeneas-style functional translation semantics model (M5 seed): Rust "
        "procedures translate into a PURE functional target - functions over "
        "immutable mathematical values with explicit separation between the "
        "speculative (return value) and erasive (modified locations) components "
        "of the post-state. Obligations under this model are total-correctness "
        "statements about the translated function, not stateful transition "
        "assertions. Registry-only seed: no adapter consumes it yet - it makes "
        "the semantics-model slot honest for future Rust/functional imports "
        "(the deferred P1.3 follow-up; harvesting stays M6, ADR 0007)."
    ),
    theories=(
        "uvil.core.int@1",
        "uvil.core.bool@1",
    ),
    profiles=("uvil.rust@1",),
    citation=(
        "Correnson, Dosch, Hermant, Jourdan. Aeneas: Rust verification by "
        "functional translation. ITP 2022."
    ),
)


class SemanticsModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, SemanticsModelEntry] = {}

    def register(self, entry: SemanticsModelEntry) -> None:
        if entry.model_id in self._models:
            raise ValueError(f"semantics model already registered: {entry.model_id}")
        self._models[entry.model_id] = entry

    def get(self, model_id: str) -> SemanticsModelEntry:
        try:
            return self._models[model_id]
        except KeyError:
            raise KeyError(f"unknown semantics model: {model_id!r}") from None

    def list(self) -> list[SemanticsModelEntry]:
        return sorted(self._models.values(), key=lambda m: m.model_id)


DEFAULT_REGISTRY = SemanticsModelRegistry()
DEFAULT_REGISTRY.register(WHY3_MEMORY_V1)
DEFAULT_REGISTRY.register(ESBMC_GOTO_V1)
DEFAULT_REGISTRY.register(STRATA_CORE_V1)
DEFAULT_REGISTRY.register(AENEAS_FUNCTIONAL_V1)
