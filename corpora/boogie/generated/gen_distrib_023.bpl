procedure p(a: int, b: int, c: int)
  requires c <= -58 && c >= -58
{
  assert (a + b) * c == a * c + b * c;
}
