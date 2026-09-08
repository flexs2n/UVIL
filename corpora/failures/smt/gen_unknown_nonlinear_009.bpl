procedure p_unknl_9(x: int, y: int)
  requires x >= 16 && y >= 17
{
  assert x * x * x != y * y * y - 1;
}
