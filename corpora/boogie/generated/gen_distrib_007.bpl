procedure p(a: int, b: int, c: int)
  requires c <= 88 && c >= 88
{
  assert (a + b) * c == a * c + b * c;
}
