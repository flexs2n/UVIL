procedure p(a: int, b: int)
  requires a >= -956 && b >= -769
{
  assert a + b == b + a;
}
