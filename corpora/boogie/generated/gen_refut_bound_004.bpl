procedure p(x: int)
  requires 0 <= x && x <= 15
{
  assert x * x >= 16;
}
