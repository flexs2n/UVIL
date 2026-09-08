procedure p(a: int, b: int)
  requires a >= -89 && b >= 185
{
  assert a + b == b + a;
}
