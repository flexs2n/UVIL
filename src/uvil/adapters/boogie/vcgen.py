"""WP VCG for the Boogie subset (`origin_backend="boogie-wp"`, ADR 0008).

Replaces the M1 invariant-context approximation: obligations are now sound
weakest-precondition sequents computed by a forward symbolic walk (Boogie's
passive form), so assignments contribute to goals, havocs rename, and loop
invariants are *obligations* (initiation + preservation) instead of assumed
facts. The pinned shapes are the discovery tests in `tests/test_vcgen.py`.

Semantics pinned there (and in ADR 0008):

- Forward walk with a variable map `vm` (source name -> current term); goals
  are substituted with `substitute` (quantifier-shadowing honored).
- `havoc x` / loop-exit renaming introduce fresh names `<name>!<n>`; `!` is
  outside the Boogie identifier charset, so a fresh name can never collide
  with a source name. A fresh name is a free variable of the sequent,
  implicitly universally quantified by the SMT validity check - exactly havoc
  semantics, no quantifier needed in the term encoding.
- `assert A` folds `A` into the path: downstream obligations assume it
  (asserts are guards in Boogie's semantics). `assert A by { B }` proves A
  under B's assumptions; B's nested asserts keep their own obligations.
- `while G invariant I1..In` emits, in program order: one initiation
  obligation (`path ⊢ I1 ∧ .. ∧ In`), body-internal assert obligations, and
  one preservation obligation (`path, I@head, G ⊢ I@end`); the exit frame
  renames the body-modified variables fresh and appends `I@exit` and `¬G` to
  the path. A loop with no invariants emits no init/preservation obligations
  and its exit frame assumes only `¬G`.
- `return;` marks the rest of the block unreachable: the path gets `false`,
  so downstream obligations are vacuous (honestly dischargeable).
- `if` statements and procedure calls stay out-of-subset (parse-time errors,
  unchanged); `ensures` clauses are recorded in the I2 contracts but produce
  no obligations (same as the M1 path; exit-code checking is future work).

The sequencing/renaming is deterministic: fresh-name counters and the
modified-variable sets are derived from program order, so the same source
always yields byte-identical obligations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...artifacts.terms import Term, TermArg
from .parser import (
    AssertStmt,
    AssignStmt,
    AssumeStmt,
    HavocStmt,
    ProcedureDecl,
    ReturnStmt,
    Stmt,
    VarStmt,
    WhileStmt,
)

Resolve = Callable[[Term], Term]


def substitute(term: Term, mapping: dict[str, Term]) -> Term:
    """Substitute variables by name; quantifier-bound names shadow the mapping."""
    op = term.op
    args = term.args
    if op == "var":
        name = args[0]
        if isinstance(name, str) and name in mapping:
            return mapping[name]
        return term
    if op in ("forall", "exists"):
        name = args[0] if args and isinstance(args[0], str) else None
        body = args[2] if len(args) > 2 else None
        inner = {k: v for k, v in mapping.items() if k != name}
        new_body = substitute(body, inner) if isinstance(body, Term) else body
        return Term(op=op, args=[args[0], args[1], new_body])
    new_args: list[TermArg] = []
    for a in args:
        new_args.append(substitute(a, mapping) if isinstance(a, Term) else a)
    return Term(op=op, args=new_args)


@dataclass
class WPObligation:
    """A verification condition: `context ⊢ goal` at one program point."""

    context: list[Term]
    goal: Term


def _and(terms: list[Term]) -> Term:
    assert terms
    if len(terms) == 1:
        return terms[0]
    return Term(op="and", args=list(terms))


class _FreshNames:
    """Deterministic fresh-name supply; `!` cannot occur in Boogie identifiers."""

    def __init__(self) -> None:
        self._n = 0

    def fresh(self, name: str) -> str:
        fresh = f"{name}!{self._n}"
        self._n += 1
        return fresh


def _modified_vars(stmts: list[Stmt]) -> set[str]:
    """Names assigned (plain or array-element) or havoc'd anywhere in `stmts`."""
    out: set[str] = set()
    for stmt in stmts:
        match stmt:
            case AssignStmt(target=(aname, _idx)):  # array-element store
                out.add(aname)
            case AssignStmt(target=str() as name):
                out.add(name)
            case HavocStmt(names=names):
                out.update(names)
            case WhileStmt(body=body):
                out |= _modified_vars(body)
            case _:
                pass
    return out


class _Walker:
    def __init__(self, sorts: dict[str, str], resolve: Resolve) -> None:
        self.fresh = _FreshNames()
        self.resolve = resolve
        # sorts is mutated: fresh names are recorded here so obligation
        # var_sorts maps them to the right SMT sort.
        self.sorts = sorts

    def _rename(self, name: str, vm: dict[str, Term]) -> Term:
        fresh = self.fresh.fresh(name)
        self.sorts[fresh] = self.sorts.get(name, "int")
        new = Term(op="var", args=[fresh])
        vm[name] = new
        return new

    def walk(
        self, stmts: list[Stmt], path: list[Term], vm: dict[str, Term], out: list[WPObligation]
    ) -> None:
        for stmt in stmts:
            match stmt:
                case AssumeStmt(term=term):
                    path.append(self.resolve(substitute(term, vm)))
                case AssertStmt(term=term, by_body=by_body):
                    goal = self.resolve(substitute(term, vm))
                    if by_body:
                        by_path = list(path)
                        by_vm = dict(vm)
                        # nested assert obligations first (program order)
                        self.walk(by_body, by_path, by_vm, out)
                        context = by_path
                    else:
                        context = list(path)
                    out.append(WPObligation(context=context, goal=goal))
                    path.append(goal)  # the assert is assumed downstream
                case AssignStmt(target=name, term=value) if isinstance(name, str):
                    vm[name] = self.resolve(substitute(value, vm))
                case AssignStmt(target=(aname, idx), term=value):
                    sort = self.sorts.get(aname, "int")
                    update_op = "seq.update" if sort == "seq" else "store"
                    base = vm.get(aname)
                    if base is None:
                        base = Term(op="var", args=[aname])
                    vm[aname] = Term(
                        op=update_op,
                        args=[
                            base,
                            self.resolve(substitute(idx, vm)),
                            self.resolve(substitute(value, vm)),
                        ],
                    )
                case HavocStmt(names=names):
                    for n in names:
                        self._rename(n, vm)
                case WhileStmt(guard=guard, invariants=invariants, body=body):
                    self._walk_while(guard, invariants, body, path, vm, out)
                case VarStmt():
                    pass
                case ReturnStmt():
                    # everything after is unreachable: vacuously satisfiable
                    path.append(Term(op="const", args=[False]))
                case _:  # pragma: no cover - all subset statements are handled
                    raise AssertionError(f"unhandled statement: {stmt!r}")

    def _walk_while(
        self,
        guard: Term,
        invariants: list[Term],
        body: list[Stmt],
        path: list[Term],
        vm: dict[str, Term],
        out: list[WPObligation],
    ) -> None:
        guard_cur = self.resolve(substitute(guard, vm))
        invs_cur = [self.resolve(substitute(i, vm)) for i in invariants]

        if invs_cur:
            # initiation: the pre-loop state establishes the invariant
            out.append(WPObligation(context=list(path), goal=_and(invs_cur)))

        # body obligations run under the loop-head frame: I ∧ G assumed
        body_path = [*path, *invs_cur, guard_cur]
        body_vm = dict(vm)
        self.walk(body, body_path, body_vm, out)

        if invs_cur:
            # preservation: I ∧ G at the head, the body re-establishes I
            invs_end = [self.resolve(substitute(i, body_vm)) for i in invariants]
            out.append(
                WPObligation(
                    context=[*path, *invs_cur, guard_cur],
                    goal=_and(invs_end),
                )
            )

        # exit frame: modified variables take fresh arbitrary values
        for name in sorted(_modified_vars(body)):
            self._rename(name, vm)
        invs_exit = [self.resolve(substitute(i, vm)) for i in invariants]
        guard_exit = self.resolve(substitute(guard, vm))
        path.extend(invs_exit)
        path.append(Term(op="not", args=[guard_exit]))


def wp_procedure(
    proc: ProcedureDecl,
    base_context: list[Term],
    sorts: dict[str, str],
    resolve: Resolve,
) -> list[WPObligation]:
    """The WP obligations of one procedure body, in program order."""
    walker = _Walker(sorts, resolve)
    out: list[WPObligation] = []
    walker.walk(proc.body, list(base_context), {}, out)
    return out
