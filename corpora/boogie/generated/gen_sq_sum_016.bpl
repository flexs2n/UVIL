procedure p(x: int, y: int)
  requires x >= 7 && y >= -50
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
