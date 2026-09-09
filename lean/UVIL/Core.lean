/-
UVIL.Core - the verified-translator groundwork (D1, M4).

The shared-theory Term AST as a deep embedding, a deep-embedded target
expression language for linear integer arithmetic (LIA), the `encodeLia`
translator, and the target denotation `LiaExpr.interp` - with a
SEMANTICS-LEVEL preservation proof: for every term in the LIA subset, the
translation preserves the term's denotation exactly
(`LiaExpr.interp e env = Term.eval t env` whenever `encodeLia t = some e`).

Scope guard (no fake universality): the LIA subset ONLY. The target language
encodes the subset restrictions IN ITS SYNTAX: `mulLit c e` is `c * e` (a
literal factor), and `divConst`/`modConst` divide by a positive constant
literal. `encodeLia` returns `none` outside the subset; anything beyond it
is documented future work (M5+), not an approximation. `Term.eval` uses
Lean's floored `/`/`%`, which agree with SMT-LIB Euclidean div/mod exactly
for positive divisors - the boundary where the shared theory and this
formalization provably coincide.

The Python mirror of this file (the producing side) lives in
`src/uvil/translate.py`; cross-language parity is pinned by tests over a
shared s-expression data format (the `uvil-translate-prove` runner in this
Lake project).
-/

namespace Uvil

/-- The shared-theory term AST (mirrors `uvil.artifacts.terms.Term` for the
LIA surface: arithmetic over `Int`; proposition positions are out of scope
here - the translator covers the arith term positions). -/
inductive Term where
  | var (name : String)
  | const (value : Int)
  | add (a b : Term)
  | sub (a b : Term)
  | mul (a b : Term)
  | neg (a : Term)
  | intdiv (a b : Term)
  | mod (a b : Term)

/-- The term denotation: the intended semantics of the shared theory. -/
def Term.eval : Term → (String → Int) → Int
  | .var n, env => env n
  | .const v, _ => v
  | .add a b, env => a.eval env + b.eval env
  | .sub a b, env => a.eval env - b.eval env
  | .mul a b, env => a.eval env * b.eval env
  | .neg a, env => -(a.eval env)
  | .intdiv a b, env => a.eval env / b.eval env
  | .mod a b, env => a.eval env % b.eval env

/-- The deep-embedded target language for LIA: the subset restrictions are
constructors (`mulLit c e` = the literal factor `c` times `e`;
`divConst k e`/`modConst k e` = division/modulo by the positive constant
`k`), so nothing outside the subset can even be expressed. -/
inductive LiaExpr where
  | var (name : String)
  | const (value : Int)
  | add (a b : LiaExpr)
  | sub (a b : LiaExpr)
  | mulLit (c : Int) (e : LiaExpr)
  | divConst (k : Int) (e : LiaExpr)
  | modConst (k : Int) (e : LiaExpr)

/-- The target denotation (the LIA backend's operational reading). -/
def LiaExpr.interp : LiaExpr → (String → Int) → Int
  | .var n, env => env n
  | .const v, _ => v
  | .add a b, env => a.interp env + b.interp env
  | .sub a b, env => a.interp env - b.interp env
  | .mulLit c e, env => c * e.interp env
  | .divConst k e, env => e.interp env / k
  | .modConst k e, env => e.interp env % k

/-- The verified translator: shared-theory term -> LIA target expression.
`none` outside the subset (fail loud upstream; nothing is approximated). -/
def Term.encodeLia : Term → Option LiaExpr
  | .var n => some (.var n)
  | .const v => some (.const v)
  | .add a b =>
    match a.encodeLia, b.encodeLia with
    | some e1, some e2 => some (.add e1 e2)
    | _, _ => none
  | .sub a b =>
    match a.encodeLia, b.encodeLia with
    | some e1, some e2 => some (.sub e1 e2)
    | _, _ => none
  | .mul a b =>
    match a.encodeLia, b.encodeLia with
    | some (.const c), some e => some (.mulLit c e)
    | some e, some (.const c) => some (.mulLit c e)
    | _, _ => none
  | .neg a => a.encodeLia.map (fun e => .sub (.const 0) e)
  | .intdiv a b =>
    match a.encodeLia, b.encodeLia with
    | some e1, some (.const k) => if k > 0 then some (.divConst k e1) else none
    | _, _ => none
  | .mod a b =>
    match a.encodeLia, b.encodeLia with
    | some e1, some (.const k) => if k > 0 then some (.modConst k e1) else none
    | _, _ => none

/-- **The preservation theorem (D1):** the translator preserves closed-term
semantics exactly - for every term in the LIA subset, the encoded target
expression denotes the same value as the term, under every valuation of the
free variables. Proof: structural induction over the term; the target's
subset-by-construction (mulLit/divConst/modConst) carries the guards. -/
theorem Term.encodeLia_preserves :
    ∀ (t : Term) (env : String → Int) (e : LiaExpr),
      t.encodeLia = some e → e.interp env = t.eval env := by
  intro t
  induction t with
  | var n =>
      intro env e h
      simp [encodeLia] at h
      cases h
      rfl
  | const v =>
      intro env e h
      simp [encodeLia] at h
      cases h
      rfl
  | add a b iha ihb =>
      intro env e h
      simp only [encodeLia] at h
      split at h
      · rename_i x_1 x_2 ea eb ha hb
        cases h
        simp [LiaExpr.interp, Term.eval, ← iha env ea ha, ← ihb env eb hb]
      · rename_i x_1 x_2 x_3
        cases h
  | sub a b iha ihb =>
      intro env e h
      simp only [encodeLia] at h
      split at h
      · rename_i x_1 x_2 ea eb ha hb
        cases h
        simp [LiaExpr.interp, Term.eval, ← iha env ea ha, ← ihb env eb hb]
      · rename_i x_1 x_2 x_3
        cases h
  | mul a b iha ihb =>
      intro env e h
      simp only [encodeLia] at h
      split at h
      · rename_i x_1 x_2 c ea ha hb
        cases h
        simp only [LiaExpr.interp, Term.eval]
        rw [ihb env ea hb, ← iha env (LiaExpr.const c) ha]
        simp [LiaExpr.interp]
      · rename_i x_1 x_2 ea c x_3 ha hb
        cases h
        simp only [LiaExpr.interp, Term.eval]
        rw [iha env ea ha, ← ihb env (LiaExpr.const c) hb]
        simp only [LiaExpr.interp]
        exact Int.mul_comm _ _
      · rename_i x_1 x_2 x_3 x_4
        cases h
  | neg a iha =>
      intro env e h
      simp only [encodeLia, Option.map_eq_some_iff] at h
      obtain ⟨ea, ha, rfl⟩ := h
      simp [LiaExpr.interp, Term.eval, iha env ea ha]
  | intdiv a b iha ihb =>
      intro env e h
      simp only [encodeLia] at h
      split at h
      · rename_i x_1 x_2 ea k ha hb
        split at h
        · cases h
          simp [LiaExpr.interp, Term.eval, ← iha env ea ha, ← ihb env (LiaExpr.const k) hb]
        · cases h
      · rename_i x_1 x_2 x_3
        cases h
  | mod a b iha ihb =>
      intro env e h
      simp only [encodeLia] at h
      split at h
      · rename_i x_1 x_2 ea k ha hb
        split at h
        · cases h
          simp [LiaExpr.interp, Term.eval, ← iha env ea ha, ← ihb env (LiaExpr.const k) hb]
        · cases h
      · rename_i x_1 x_2 x_3
        cases h

end Uvil
