procedure p(a: int, b: int)
  requires a >= -923 && b >= -50
{
  assert a + b == b + a;
}
