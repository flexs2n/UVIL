procedure p(a: int, b: int, c: int)
  requires c <= 0 && c >= 0
{
  assert (a + b) * c == a * c + b * c;
}
