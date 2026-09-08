procedure p(a: int, b: int)
  requires a <= 277 && b <= 256
{
  assert (if a < b then a else b) <= 277;
}
