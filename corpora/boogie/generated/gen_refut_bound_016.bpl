procedure p(x: int)
  requires 0 <= x && x <= 14
{
  assert x * x >= 15;
}
