procedure p(a: int, b: int)
  requires a <= 476 && b <= 185
{
  assert (if a < b then a else b) <= 476;
}
