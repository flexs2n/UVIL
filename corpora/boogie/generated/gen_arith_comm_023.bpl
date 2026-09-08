procedure p(a: int, b: int)
  requires a >= 698 && b >= -303
{
  assert a + b == b + a;
}
