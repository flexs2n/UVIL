procedure p(x: int)
  requires 0 <= x && x <= 7
{
  assert x * x >= 8;
}
