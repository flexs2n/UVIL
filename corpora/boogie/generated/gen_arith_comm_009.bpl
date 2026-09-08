procedure p(a: int, b: int)
  requires a >= 445 && b >= -146
{
  assert a + b == b + a;
}
