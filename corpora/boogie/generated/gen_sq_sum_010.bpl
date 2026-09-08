procedure p(x: int, y: int)
  requires x >= 13 && y >= -1
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
