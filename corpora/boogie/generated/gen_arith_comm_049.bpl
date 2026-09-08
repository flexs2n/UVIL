procedure p(a: int, b: int)
  requires a >= 89 && b >= -431
{
  assert a + b == b + a;
}
