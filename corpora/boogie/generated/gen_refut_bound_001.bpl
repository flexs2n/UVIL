procedure p(x: int)
  requires 0 <= x && x <= 6
{
  assert x * x >= 7;
}
