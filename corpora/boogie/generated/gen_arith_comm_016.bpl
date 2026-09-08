procedure p(a: int, b: int)
  requires a >= -836 && b >= -758
{
  assert a + b == b + a;
}
