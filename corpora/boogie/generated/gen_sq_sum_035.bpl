procedure p(x: int, y: int)
  requires x >= -10 && y >= -39
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
