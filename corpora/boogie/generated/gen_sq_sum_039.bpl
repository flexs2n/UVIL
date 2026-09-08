procedure p(x: int, y: int)
  requires x >= 19 && y >= -42
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
