procedure p(x: int, y: int)
  requires x >= 16 && y >= 1
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
