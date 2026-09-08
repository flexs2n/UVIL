procedure p(a: int, b: int)
  requires a >= -458 && b >= -893
{
  assert a + b == b + a;
}
