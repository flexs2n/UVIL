procedure p(a: int, b: int)
  requires a <= 275 && b <= 515
{
  assert (if a < b then a else b) <= 515;
}
