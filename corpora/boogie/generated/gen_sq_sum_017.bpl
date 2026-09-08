procedure p(x: int, y: int)
  requires x >= -47 && y >= -29
{
  assert (x + y) * (x + y) == x * x + 2 * x * y + y * y;
}
