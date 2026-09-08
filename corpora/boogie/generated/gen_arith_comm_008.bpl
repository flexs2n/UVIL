procedure p(a: int, b: int)
  requires a >= 976 && b >= 545
{
  assert a + b == b + a;
}
