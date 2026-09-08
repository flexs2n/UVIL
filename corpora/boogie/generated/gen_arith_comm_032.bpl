procedure p(a: int, b: int)
  requires a >= 257 && b >= 137
{
  assert a + b == b + a;
}
