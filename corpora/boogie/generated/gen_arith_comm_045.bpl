procedure p(a: int, b: int)
  requires a >= 923 && b >= 569
{
  assert a + b == b + a;
}
