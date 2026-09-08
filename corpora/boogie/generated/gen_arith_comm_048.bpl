procedure p(a: int, b: int)
  requires a >= -384 && b >= -123
{
  assert a + b == b + a;
}
