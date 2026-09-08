procedure p(a: int, b: int)
  requires a <= 140 && b <= 197
{
  assert (if a < b then a else b) <= 197;
}
