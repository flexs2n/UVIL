procedure p(a: int, b: int)
  requires a <= 153 && b <= 103
{
  assert (if a < b then a else b) <= 153;
}
