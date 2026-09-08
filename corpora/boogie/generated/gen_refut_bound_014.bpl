procedure p(x: int)
  requires 0 <= x && x <= 46
{
  assert x * x >= 47;
}
