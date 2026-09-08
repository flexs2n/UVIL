procedure p(x: int)
  requires 0 <= x && x <= 58
{
  assert x * x >= 59;
}
