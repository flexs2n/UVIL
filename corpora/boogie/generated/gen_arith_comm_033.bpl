procedure p(a: int, b: int)
  requires a >= 54 && b >= 267
{
  assert a + b == b + a;
}
