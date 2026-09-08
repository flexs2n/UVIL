procedure p(a: int, b: int, c: int)
  requires c <= 94 && c >= 94
{
  assert (a + b) * c == a * c + b * c;
}
