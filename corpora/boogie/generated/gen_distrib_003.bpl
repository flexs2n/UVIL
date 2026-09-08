procedure p(a: int, b: int, c: int)
  requires c <= 24 && c >= 24
{
  assert (a + b) * c == a * c + b * c;
}
