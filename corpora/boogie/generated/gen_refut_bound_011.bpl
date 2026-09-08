procedure p(x: int)
  requires 0 <= x && x <= 19
{
  assert x * x >= 20;
}
