procedure p(a: int, b: int)
  requires a >= 286 && b >= 438
{
  assert a + b == b + a;
}
