procedure p(a: int, b: int)
  requires a >= 561 && b >= -253
{
  assert a + b == b + a;
}
