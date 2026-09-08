procedure p(a: int, b: int)
  requires a <= 324 && b <= 373
{
  assert (if a < b then a else b) <= 373;
}
