procedure p(x: int)
  requires 0 <= x && x <= 28
{
  assert x * x >= 29;
}
