procedure p(a: int, b: int)
  requires a >= -502 && b >= 734
{
  assert a + b == b + a;
}
