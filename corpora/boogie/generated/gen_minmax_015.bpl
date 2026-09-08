procedure p(a: int, b: int)
  requires a <= 234 && b <= 335
{
  assert (if a < b then a else b) <= 335;
}
