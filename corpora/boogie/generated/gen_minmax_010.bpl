procedure p(a: int, b: int)
  requires a <= 516 && b <= 380
{
  assert (if a < b then a else b) <= 516;
}
