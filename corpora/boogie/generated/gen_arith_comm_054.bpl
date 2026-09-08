procedure p(a: int, b: int)
  requires a >= -781 && b >= 119
{
  assert a + b == b + a;
}
