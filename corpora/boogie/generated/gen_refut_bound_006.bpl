procedure p(x: int)
  requires 0 <= x && x <= 25
{
  assert x * x >= 26;
}
