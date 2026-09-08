procedure p(x: int)
  requires 0 <= x && x <= 39
{
  assert x * x >= 40;
}
