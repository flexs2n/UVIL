procedure p(x: int, y: int)
  requires x >= 23 && y >= -26
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
