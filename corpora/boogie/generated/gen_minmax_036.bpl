procedure p(a: int, b: int)
  requires a <= 220 && b <= 374
{
  assert (if a < b then a else b) <= 374;
}
