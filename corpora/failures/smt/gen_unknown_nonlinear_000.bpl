procedure p_unknl_0(x: int, y: int)
  requires x >= 7 && y >= 8
{
  assert x * x * x != y * y * y - 1;
}
