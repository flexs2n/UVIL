procedure p(a: int, b: int)
  requires a >= 720 && b >= -882
{
  assert a + b == b + a;
}
