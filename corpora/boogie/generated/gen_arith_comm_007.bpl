procedure p(a: int, b: int)
  requires a >= 799 && b >= -600
{
  assert a + b == b + a;
}
