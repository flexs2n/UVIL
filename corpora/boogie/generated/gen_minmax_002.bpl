procedure p(a: int, b: int)
  requires a <= 132 && b <= 157
{
  assert (if a < b then a else b) <= 157;
}
