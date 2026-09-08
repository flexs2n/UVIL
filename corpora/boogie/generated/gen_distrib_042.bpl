procedure p(a: int, b: int, c: int)
  requires c <= 50 && c >= 50
{
  assert (a + b) * c == a * c + b * c;
}
