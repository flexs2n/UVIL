procedure p(x: int)
  requires 0 <= x && x <= 22
{
  assert x * x >= 23;
}
