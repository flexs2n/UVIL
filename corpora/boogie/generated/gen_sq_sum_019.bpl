procedure p(x: int, y: int)
  requires x >= -21 && y >= 23
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
