procedure p(a: int, b: int)
  requires a <= 268 && b <= 319
{
  assert (if a < b then a else b) <= 319;
}
