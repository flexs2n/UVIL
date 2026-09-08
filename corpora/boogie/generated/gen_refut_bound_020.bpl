procedure p(x: int)
  requires 0 <= x && x <= 59
{
  assert x * x >= 60;
}
