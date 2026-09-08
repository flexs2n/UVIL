procedure p(a: int, b: int)
  requires a >= -820 && b >= 994
{
  assert a + b == b + a;
}
