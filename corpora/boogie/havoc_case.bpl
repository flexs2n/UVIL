// havoc drops assumptions about the havoc'd variable (M1 approximation);
// with the assumption dropped, x is unconstrained and the goal is refuted
procedure havoc_then_use(x: int)
{
  assume x >= 100;
  havoc x;
  assert x >= 100;
}
