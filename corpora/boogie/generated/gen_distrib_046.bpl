procedure p(a: int, b: int, c: int)
  requires c <= -60 && c >= -60
{
  assert (a + b) * c == a * c + b * c;
}
