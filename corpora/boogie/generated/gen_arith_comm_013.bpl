procedure p(a: int, b: int)
  requires a >= -436 && b >= 14
{
  assert a + b == b + a;
}
