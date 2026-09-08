procedure p(a: int, b: int)
  requires a >= -9 && b >= -772
{
  assert a + b == b + a;
}
