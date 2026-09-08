procedure p(a: int, b: int)
  requires a <= 268 && b <= 108
{
  assert (if a < b then a else b) <= 268;
}
