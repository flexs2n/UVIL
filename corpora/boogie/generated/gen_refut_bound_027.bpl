procedure p(x: int)
  requires 0 <= x && x <= 21
{
  assert x * x >= 22;
}
