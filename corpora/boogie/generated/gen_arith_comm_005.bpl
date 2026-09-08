procedure p(a: int, b: int)
  requires a >= 33 && b >= -567
{
  assert a + b == b + a;
}
