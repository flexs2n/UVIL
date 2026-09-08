procedure p(a: int, b: int)
  requires a >= -279 && b >= -743
{
  assert a + b == b + a;
}
