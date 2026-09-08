procedure p(a: int, b: int)
  requires a >= 699 && b >= 702
{
  assert a + b == b + a;
}
