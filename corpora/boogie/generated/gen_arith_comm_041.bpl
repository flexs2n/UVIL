procedure p(a: int, b: int)
  requires a >= -753 && b >= 296
{
  assert a + b == b + a;
}
