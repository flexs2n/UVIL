// axioms and const definitions join every obligation's context
const MAX: int := 100;
axiom A_MAX_POS: MAX > 0;

procedure uses_axiom(x: int)
  requires x <= MAX
{
  assert MAX >= 1;
}
