procedure p(a: int, b: int, c: int)
  requires c <= 55 && c >= 55
{
  assert (a + b) * c == a * c + b * c;
}
