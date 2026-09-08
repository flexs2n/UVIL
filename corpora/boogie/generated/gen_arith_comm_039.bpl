procedure p(a: int, b: int)
  requires a >= 253 && b >= 705
{
  assert a + b == b + a;
}
