procedure p(a: int, b: int)
  requires a <= 83 && b <= 65
{
  assert (if a < b then a else b) <= 83;
}
