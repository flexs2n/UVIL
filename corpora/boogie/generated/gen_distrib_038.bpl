procedure p(a: int, b: int, c: int)
  requires c <= -37 && c >= -37
{
  assert (a + b) * c == a * c + b * c;
}
