procedure p(a: int, b: int)
  requires a <= 258 && b <= 306
{
  assert (if a < b then a else b) <= 306;
}
