procedure p(x: int, y: int)
  requires x >= 9 && y >= -2
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
