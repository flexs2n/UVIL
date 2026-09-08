procedure p(a: int, b: int)
  requires a >= 613 && b >= 703
{
  assert a + b == b + a;
}
