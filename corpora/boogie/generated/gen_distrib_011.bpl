procedure p(a: int, b: int, c: int)
  requires c <= -56 && c >= -56
{
  assert (a + b) * c == a * c + b * c;
}
