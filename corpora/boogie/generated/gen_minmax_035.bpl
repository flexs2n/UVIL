procedure p(a: int, b: int)
  requires a <= 208 && b <= 256
{
  assert (if a < b then a else b) <= 256;
}
