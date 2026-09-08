procedure p(x: int, y: int)
  requires x >= 6 && y >= 0
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
