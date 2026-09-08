procedure p(a: int, b: int, c: int)
  requires c <= 26 && c >= 26
{
  assert (a + b) * c == a * c + b * c;
}
