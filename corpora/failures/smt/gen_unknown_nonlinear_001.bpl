procedure p_unknl_1(x: int, y: int)
  requires x >= 8 && y >= 9
{
  assert x * x * x != y * y * y - 1;
}
