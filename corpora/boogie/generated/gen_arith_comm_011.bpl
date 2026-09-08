procedure p(a: int, b: int)
  requires a >= 496 && b >= -144
{
  assert a + b == b + a;
}
