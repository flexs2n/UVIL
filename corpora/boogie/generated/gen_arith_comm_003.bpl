procedure p(a: int, b: int)
  requires a >= -488 && b >= -976
{
  assert a + b == b + a;
}
