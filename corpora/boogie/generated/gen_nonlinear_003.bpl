procedure p(x: int, y: int)
  requires x >= 9 && y >= 13
{
  assert x * x * x == y * y * y + 1;
}
