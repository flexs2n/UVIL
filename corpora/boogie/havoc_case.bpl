// havoc renames the variable (WP VCG, ADR 0008): the goal is over a fresh
// value, so the pre-havoc assumption cannot constrain it and the goal is refuted
procedure havoc_then_use(x: int)
{
  assume x >= 100;
  havoc x;
  assert x >= 100;
}
