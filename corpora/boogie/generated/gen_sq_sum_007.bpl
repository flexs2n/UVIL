procedure p(x: int, y: int)
  requires x >= 8 && y >= -37
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
