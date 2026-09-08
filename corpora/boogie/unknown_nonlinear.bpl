// nonlinear integer family: z3 reliably returns unknown within budget
procedure cubic_shift(x: int, y: int)
  requires x >= 7 && y >= 7
{
  assert x * x * x == y * y * y + 1;
}
