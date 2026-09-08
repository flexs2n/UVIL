procedure p(a: int, b: int)
  requires a >= -112 && b >= 778
{
  assert a + b == b + a;
}
