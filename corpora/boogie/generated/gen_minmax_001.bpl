procedure p(a: int, b: int)
  requires a <= 311 && b <= 464
{
  assert (if a < b then a else b) <= 464;
}
