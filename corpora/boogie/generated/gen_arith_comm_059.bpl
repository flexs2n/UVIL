procedure p(a: int, b: int)
  requires a >= -116 && b >= -620
{
  assert a + b == b + a;
}
