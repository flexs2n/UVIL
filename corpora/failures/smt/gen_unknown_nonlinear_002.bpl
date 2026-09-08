procedure p_unknl_2(x: int, y: int)
  requires x >= 9 && y >= 10
{
  assert x * x * x != y * y * y - 1;
}
