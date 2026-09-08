procedure p(a: int, b: int, c: int)
  requires c <= 10 && c >= 10
{
  assert (a + b) * c == a * c + b * c;
}
