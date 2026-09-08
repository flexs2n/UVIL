procedure p(x: int, y: int)
  requires x >= -14 && y >= -16
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
