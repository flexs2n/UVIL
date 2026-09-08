procedure p(x: int, y: int)
  requires x >= -42 && y >= 8
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
