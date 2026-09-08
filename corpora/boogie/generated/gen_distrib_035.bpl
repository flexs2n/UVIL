procedure p(a: int, b: int, c: int)
  requires c <= 85 && c >= 85
{
  assert (a + b) * c == a * c + b * c;
}
