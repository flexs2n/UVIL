procedure p(a: int, b: int)
  requires a >= -392 && b >= 224
{
  assert a + b == b + a;
}
