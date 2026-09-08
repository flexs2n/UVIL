procedure p(a: int, b: int)
  requires a >= 793 && b >= -253
{
  assert a + b == b + a;
}
