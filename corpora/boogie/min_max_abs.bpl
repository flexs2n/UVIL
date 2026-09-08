// min/max family
procedure min_le(a: int, b: int, m: int)
  requires a <= m && b <= m
{
  assert (if a < b then a else b) <= m;
}

procedure max_ge(a: int, b: int, m: int)
  requires a >= m && b >= m
{
  assert (if a < b then b else a) >= m;
}
