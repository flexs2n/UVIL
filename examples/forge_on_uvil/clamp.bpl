/* Forge-demo: the distilled Boogie encoding of the clamp property, AS AN
   AGENT WOULD FIRST WRITE IT (assuming a correct clamp: c = 10 above).
   The distilled model mirrors the C bug faithfully (the clamp returns 9
   where C returns 9): z3 REFUTES the property with the same
   counterexample family (x = 11). */
procedure clamp10(x : int) returns (c : int)
  requires x >= 0 && x <= 100
  ensures c == 10 || c == x
{
  c := if x > 10 then 9 else (if x < 0 then 0 else x);
  assert (if x > 10 then 9 else (if x < 0 then 0 else x)) == 10
      || (if x > 10 then 9 else (if x < 0 then 0 else x)) == x;
}
