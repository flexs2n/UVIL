procedure p(x: int)
  requires 0 <= x && x <= 49
{
  assert x * x >= 50;
}
