procedure p(a: int, b: int)
  requires a <= 181 && b <= 171
{
  assert (if a < b then a else b) <= 181;
}
