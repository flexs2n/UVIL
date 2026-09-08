procedure p(a: int, b: int, c: int)
  requires c <= 74 && c >= 74
{
  assert (a + b) * c == a * c + b * c;
}
