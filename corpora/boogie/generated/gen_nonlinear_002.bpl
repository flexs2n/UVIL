procedure p(x: int, y: int)
  requires x >= 7 && y >= 11
{
  assert x * x * x == y * y * y + 1;
}
