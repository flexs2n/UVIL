procedure p_unknl_6(x: int, y: int)
  requires x >= 13 && y >= 14
{
  assert x * x * x != y * y * y - 1;
}
