procedure p_unknl_7(x: int, y: int)
  requires x >= 14 && y >= 15
{
  assert x * x * x != y * y * y - 1;
}
