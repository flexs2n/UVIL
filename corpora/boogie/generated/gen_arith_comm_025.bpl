procedure p(a: int, b: int)
  requires a >= -672 && b >= 892
{
  assert a + b == b + a;
}
