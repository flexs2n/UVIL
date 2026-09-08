procedure p(a: int, b: int)
  requires a >= -90 && b >= 358
{
  assert a + b == b + a;
}
