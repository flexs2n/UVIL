procedure p(a: int, b: int)
  requires a <= 456 && b <= 573
{
  assert (if a < b then a else b) <= 573;
}
