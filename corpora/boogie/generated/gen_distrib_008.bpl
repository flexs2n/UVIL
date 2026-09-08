procedure p(a: int, b: int, c: int)
  requires c <= -71 && c >= -71
{
  assert (a + b) * c == a * c + b * c;
}
