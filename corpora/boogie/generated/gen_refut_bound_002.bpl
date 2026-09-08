procedure p(x: int)
  requires 0 <= x && x <= 38
{
  assert x * x >= 39;
}
