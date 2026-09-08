procedure p_unknl_3(x: int, y: int)
  requires x >= 10 && y >= 11
{
  assert x * x * x != y * y * y - 1;
}
