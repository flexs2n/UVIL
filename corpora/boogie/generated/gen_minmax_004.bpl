procedure p(a: int, b: int)
  requires a <= 341 && b <= 369
{
  assert (if a < b then a else b) <= 369;
}
