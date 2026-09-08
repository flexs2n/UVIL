procedure p(a: int, b: int)
  requires a >= 157 && b >= 159
{
  assert a + b == b + a;
}
