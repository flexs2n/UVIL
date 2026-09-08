// negative-literal reasoning
procedure negatives_lt(a: int)
  requires a <= -3
{
  assert a < 0;
}

procedure negatives_pos(a: int)
  requires a <= -3
{
  assert -a > 0;
}

procedure neg_mul(a: int, b: int)
  requires a >= 1 && b >= 1
{
  assert (-a) * b < 0;
}
