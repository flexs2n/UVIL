procedure p(x: int, y: int)
  requires x >= -34 && y >= 40
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
