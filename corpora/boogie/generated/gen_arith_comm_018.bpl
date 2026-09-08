procedure p(a: int, b: int)
  requires a >= -253 && b >= -418
{
  assert a + b == b + a;
}
