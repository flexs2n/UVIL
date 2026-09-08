procedure p(a: int, b: int, c: int)
  requires c <= -89 && c >= -89
{
  assert (a + b) * c == a * c + b * c;
}
