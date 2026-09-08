procedure p(a: int, b: int)
  requires a <= 265 && b <= 129
{
  assert (if a < b then a else b) <= 265;
}
