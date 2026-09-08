procedure p(a: int, b: int, c: int)
  requires c <= 43 && c >= 43
{
  assert (a + b) * c == a * c + b * c;
}
