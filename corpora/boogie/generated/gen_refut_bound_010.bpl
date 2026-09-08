procedure p(x: int)
  requires 0 <= x && x <= 48
{
  assert x * x >= 49;
}
