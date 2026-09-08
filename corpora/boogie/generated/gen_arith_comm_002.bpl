procedure p(a: int, b: int)
  requires a >= 281 && b >= -44
{
  assert a + b == b + a;
}
