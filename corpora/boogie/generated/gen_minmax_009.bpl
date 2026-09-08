procedure p(a: int, b: int)
  requires a <= 116 && b <= 152
{
  assert (if a < b then a else b) <= 152;
}
