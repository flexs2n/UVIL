procedure p(a: int, b: int)
  requires a <= 108 && b <= 164
{
  assert (if a < b then a else b) <= 164;
}
