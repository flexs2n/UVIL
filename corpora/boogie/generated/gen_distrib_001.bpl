procedure p(a: int, b: int, c: int)
  requires c <= -12 && c >= -12
{
  assert (a + b) * c == a * c + b * c;
}
