procedure p(x: int, y: int)
  requires x >= 17 && y >= 10
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
