procedure p(x: int, y: int)
  requires x >= -25 && y >= -5
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
