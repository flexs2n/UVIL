procedure p(a: int, b: int)
  requires a >= 745 && b >= 161
{
  assert a + b == b + a;
}
