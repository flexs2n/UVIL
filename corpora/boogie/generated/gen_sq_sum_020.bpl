procedure p(x: int, y: int)
  requires x >= 40 && y >= -32
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
