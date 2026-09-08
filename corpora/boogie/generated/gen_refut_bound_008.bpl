procedure p(x: int)
  requires 0 <= x && x <= 36
{
  assert x * x >= 37;
}
