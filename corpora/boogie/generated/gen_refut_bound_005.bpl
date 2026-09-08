procedure p(x: int)
  requires 0 <= x && x <= 32
{
  assert x * x >= 33;
}
