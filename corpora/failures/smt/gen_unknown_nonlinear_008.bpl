procedure p_unknl_8(x: int, y: int)
  requires x >= 15 && y >= 16
{
  assert x * x * x != y * y * y - 1;
}
