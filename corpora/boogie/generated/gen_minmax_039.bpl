procedure p(a: int, b: int)
  requires a <= 377 && b <= 565
{
  assert (if a < b then a else b) <= 565;
}
