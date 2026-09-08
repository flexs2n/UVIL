procedure p(x: int, y: int)
  requires x >= 4 && y >= -33
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
