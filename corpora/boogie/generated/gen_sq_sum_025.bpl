procedure p(x: int, y: int)
  requires x >= -44 && y >= 19
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
