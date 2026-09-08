procedure p(a: int, b: int)
  requires a >= 244 && b >= 201
{
  assert a + b == b + a;
}
