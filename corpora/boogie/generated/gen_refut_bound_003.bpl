procedure p(x: int)
  requires 0 <= x && x <= 16
{
  assert x * x >= 17;
}
