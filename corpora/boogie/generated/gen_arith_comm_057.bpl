procedure p(a: int, b: int)
  requires a >= 910 && b >= -140
{
  assert a + b == b + a;
}
