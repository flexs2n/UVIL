procedure p(a: int, b: int)
  requires a >= -160 && b >= -597
{
  assert a + b == b + a;
}
