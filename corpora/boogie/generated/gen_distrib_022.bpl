procedure p(a: int, b: int, c: int)
  requires c <= 64 && c >= 64
{
  assert (a + b) * c == a * c + b * c;
}
