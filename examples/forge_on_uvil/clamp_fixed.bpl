/* Forge-demo: the REPAIRED encoding - the counterexample-driven repair (M2
   harness) corrects the mirrored bug, and the property discharges; the Lean
   and Isabelle twins then attest the same sequent. */
procedure clamp10(x : int) returns (c : int)
  requires x >= 0 && x <= 100
  ensures c == 10 || c == x
{
  c := if x > 10 then 10 else (if x < 0 then 0 else x);
  assert (if x > 10 then 10 else (if x < 0 then 0 else x)) == 10
      || (if x > 10 then 10 else (if x < 0 then 0 else x)) == x;
}
