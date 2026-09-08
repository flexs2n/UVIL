procedure p(a: int, b: int)
  requires a >= -756 && b >= 307
{
  assert a + b == b + a;
}
