procedure p(a: int, b: int)
  requires a >= 784 && b >= -950
{
  assert a + b == b + a;
}
