procedure p(a: int, b: int)
  requires a <= 161 && b <= 190
{
  assert (if a < b then a else b) <= 190;
}
