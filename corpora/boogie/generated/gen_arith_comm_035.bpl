procedure p(a: int, b: int)
  requires a >= -334 && b >= -923
{
  assert a + b == b + a;
}
