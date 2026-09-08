procedure p_unknl_4(x: int, y: int)
  requires x >= 11 && y >= 12
{
  assert x * x * x != y * y * y - 1;
}
