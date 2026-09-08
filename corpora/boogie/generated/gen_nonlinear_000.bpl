procedure p(x: int, y: int)
  requires x >= 10 && y >= 8
{
  assert x * x * x == y * y * y + 1;
}
