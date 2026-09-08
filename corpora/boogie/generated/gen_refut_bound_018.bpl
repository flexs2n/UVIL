procedure p(x: int)
  requires 0 <= x && x <= 23
{
  assert x * x >= 24;
}
