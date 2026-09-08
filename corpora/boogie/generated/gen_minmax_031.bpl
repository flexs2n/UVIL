procedure p(a: int, b: int)
  requires a <= 300 && b <= 86
{
  assert (if a < b then a else b) <= 300;
}
