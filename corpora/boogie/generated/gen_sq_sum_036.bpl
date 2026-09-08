procedure p(x: int, y: int)
  requires x >= 35 && y >= -41
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
