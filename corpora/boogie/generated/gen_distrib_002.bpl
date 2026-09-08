procedure p(a: int, b: int, c: int)
  requires c <= -77 && c >= -77
{
  assert (a + b) * c == a * c + b * c;
}
