procedure p(a: int, b: int, c: int)
  requires c <= -91 && c >= -91
{
  assert (a + b) * c == a * c + b * c;
}
