procedure p(a: int, b: int)
  requires a >= 933 && b >= -300
{
  assert a + b == b + a;
}
