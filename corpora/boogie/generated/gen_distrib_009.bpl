procedure p(a: int, b: int, c: int)
  requires c <= -83 && c >= -83
{
  assert (a + b) * c == a * c + b * c;
}
