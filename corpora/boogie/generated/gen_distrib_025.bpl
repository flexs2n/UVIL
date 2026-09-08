procedure p(a: int, b: int, c: int)
  requires c <= 17 && c >= 17
{
  assert (a + b) * c == a * c + b * c;
}
