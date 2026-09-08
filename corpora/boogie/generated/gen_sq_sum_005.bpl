procedure p(x: int, y: int)
  requires x >= 20 && y >= -44
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
