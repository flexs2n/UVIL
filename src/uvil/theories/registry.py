"""Core theory registry.

Theories are named, versioned, citable entries describing the sorts and operators
they contribute to the core assertion language. Registered from day one:
`uvil.core.bool`, `uvil.core.int`, `uvil.core.real`, `uvil.core.array`,
`uvil.core.bitvec`, `uvil.core.adt`, `uvil.core.seq`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TheoryEntry:
    name: str
    version: str
    description: str
    sorts: tuple[str, ...] = ()
    ops: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class TheoryRef:
    name: str
    version: str

    @classmethod
    def parse(cls, ref: str) -> TheoryRef:
        if "@" not in ref:
            raise ValueError(f"theory ref must be 'name@version', got {ref!r}")
        name, version = ref.rsplit("@", 1)
        return cls(name=name, version=version)


CORE_THEORIES: tuple[TheoryEntry, ...] = (
    TheoryEntry(
        name="uvil.core.bool",
        version="1",
        description="Boolean values and propositional connectives",
        sorts=("bool",),
        ops=("and", "or", "not", "implies", "eq"),
    ),
    TheoryEntry(
        name="uvil.core.int",
        version="1",
        description="Unbounded integers (SMT-LIB Int)",
        sorts=("int",),
        ops=("add", "sub", "mul", "neg", "intdiv", "mod", "lt", "le", "gt", "ge", "eq"),
    ),
    TheoryEntry(
        name="uvil.core.real",
        version="1",
        description="Reals (SMT-LIB Real)",
        sorts=("real",),
        ops=("add", "sub", "mul", "neg", "realdiv", "lt", "le", "gt", "ge", "eq"),
    ),
    TheoryEntry(
        name="uvil.core.array",
        version="1",
        description="Parameterized arrays (SMT-LIB Array)",
        sorts=("array",),
        ops=("select", "store", "eq"),
    ),
    TheoryEntry(
        name="uvil.core.bitvec",
        version="1",
        description="Fixed-width bitvectors (SMT-LIB BitVec)",
        sorts=("bitvec",),
        ops=("add", "sub", "mul", "eq"),
    ),
    TheoryEntry(
        name="uvil.core.adt",
        version="1",
        description="Algebraic data types (SMT-LIB Datatype)",
        sorts=("adt",),
        ops=("eq",),
    ),
    TheoryEntry(
        name="uvil.core.seq",
        version="1",
        description="Sequences (SMT-LIB Seq)",
        sorts=("seq",),
        ops=("seq.empty", "seq.cons", "seq.len", "seq.nth", "seq.update", "eq"),
    ),
)


class TheoryRegistry:
    def __init__(self) -> None:
        self._theories: dict[str, TheoryEntry] = {}
        for entry in CORE_THEORIES:
            self.register(entry)

    def register(self, entry: TheoryEntry) -> None:
        key = f"{entry.name}@{entry.version}"
        if key in self._theories:
            raise ValueError(f"theory already registered: {key}")
        self._theories[key] = entry

    def get(self, ref: str) -> TheoryEntry:
        key = ref
        if "@" not in key:
            candidates = [k for k in self._theories if k.rsplit("@", 1)[0] == ref]
            if len(candidates) != 1:
                raise KeyError(f"theory ref {ref!r} is ambiguous or unknown: {candidates}")
            key = candidates[0]
        try:
            return self._theories[key]
        except KeyError:
            raise KeyError(f"unknown theory: {ref!r}") from None

    def list(self) -> list[TheoryEntry]:
        return sorted(self._theories.values(), key=lambda e: (e.name, e.version))


DEFAULT_REGISTRY = TheoryRegistry()
