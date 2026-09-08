procedure p_unknl_5(x: int, y: int)
  requires x >= 12 && y >= 13
{
  assert x * x * x != y * y * y - 1;
}
