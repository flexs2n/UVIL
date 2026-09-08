procedure p(a: int, b: int)
  requires a >= 514 && b >= -484
{
  assert a + b == b + a;
}
