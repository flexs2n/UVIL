procedure p(x: int, y: int)
  requires x >= 45 && y >= -6
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
