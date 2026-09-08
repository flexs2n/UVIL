procedure p(a: int, b: int, c: int)
  requires c <= 22 && c >= 22
{
  assert (a + b) * c == a * c + b * c;
}
