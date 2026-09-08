procedure p(a: int, b: int)
  requires a >= 667 && b >= -8
{
  assert a + b == b + a;
}
