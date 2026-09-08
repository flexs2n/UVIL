procedure p(a: int, b: int)
  requires a >= 53 && b >= -729
{
  assert a + b == b + a;
}
