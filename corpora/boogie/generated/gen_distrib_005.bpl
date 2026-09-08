procedure p(a: int, b: int, c: int)
  requires c <= -48 && c >= -48
{
  assert (a + b) * c == a * c + b * c;
}
