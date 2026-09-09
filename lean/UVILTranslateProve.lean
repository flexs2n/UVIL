/-
UVILTranslateProve - the D1 parity runner (M4).

Reads fixture lines from stdin, one per term:
    SEXPR | env
where SEXPR is the s-expression form of a shared-theory `Term`
(`(var x)`, `(const 3)`, `(add T T)`, `(sub T T)`, `(mul T T)`, `(neg T)`,
`(div T T)`, `(mod T T)`) and env is `k=v,k2=v2` (unbound variables read 0).
For each line prints one status line:
    some <interp> <eval>   - term in the LIA subset; interp (encodeLia t)
                             and eval t, which the preservation theorem
                             proves equal
    none                   - term outside the LIA subset
    error <msg>            - malformed line

The Python side (src/uvil/translate.py) computes the same values; agreement
is pinned by tests/test_translator.py.
-/

import UVIL.Core

open Uvil

def lex (s : String) : List String :=
  let padded := s.replace "\n" " " |>.replace "\r" " " |>.replace "\t" " "
    |>.replace "(" " ( " |>.replace ")" " ) "
  (padded.splitOn " ").filter (· ≠ "")

def isWs (c : Char) : Bool := c == ' ' || c == '\t' || c == '\r' || c == '\n'

def trimS (s : String) : String := (s.dropWhile isWs).dropRightWhile isWs |>.toString

def mkOp (op : String) (a b : Term) : Term :=
  match op with
  | "add" => Term.add a b
  | "sub" => Term.sub a b
  | "mul" => Term.mul a b
  | "div" => Term.intdiv a b
  | "mod" => Term.mod a b
  | other => Term.var s!"<bad-op:{other}>"

partial def parseTerm (toks : List String) : Except String (Term × List String) :=
  match toks with
  | "(" :: "var" :: name :: ")" :: rest => .ok (Term.var name, rest)
  | "(" :: "const" :: n :: ")" :: rest =>
      match n.toInt? with
      | some v => .ok (Term.const v, rest)
      | none => .error s!"bad const {n}"
  | "(" :: "neg" :: rest =>
      match parseTerm rest with
      | .error msg => .error msg
      | .ok (a, ")" :: rest') => .ok (Term.neg a, rest')
      | _ => .error "expected ')'"
  | "(" :: op :: rest =>
      match parseTerm rest with
      | .error msg => .error msg
      | .ok (a, r1) =>
        match parseTerm r1 with
        | .error msg => .error msg
        | .ok (b, r2) =>
          match r2 with
          | ")" :: rest => .ok (mkOp op a b, rest)
          | _ => .error "expected ')'"
  | _ => .error "malformed term"

def parseEnv (s : String) : String → Int :=
  let pairs := (s.splitOn ",").map trimS |>.filter (· ≠ "")
  fun name =>
    pairs.foldl (fun acc p =>
      match p.splitOn "=" with
      | [k, v] => if k == name then (v.toInt? |>.getD 0) else acc
      | _ => acc) 0

partial def readAll (h : IO.FS.Stream) : IO String := do
  let l ← h.getLine
  if l.isEmpty then return ""
  let rest ← readAll h
  return l ++ rest

def evalLine (line : String) : String :=
  let line := trimS line
  if line.isEmpty then ""
  else
    match line.splitOn "|" with
    | [sexprS, envS] =>
        match parseTerm (lex sexprS) with
        | .error msg => s!"error {msg}"
        | .ok (t, _) =>
            let env := parseEnv envS
            match t.encodeLia with
            | none => "none"
            | some e => s!"some {e.interp env} {t.eval env}"
    | _ => "error malformed-line"

def main : IO Unit := do
  let stdin ← IO.getStdin
  let input ← readAll stdin
  for line in input.splitOn "\n" do
    let out := evalLine line
    if !out.isEmpty then
      IO.println out
