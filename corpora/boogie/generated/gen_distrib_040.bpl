procedure p(a: int, b: int, c: int)
  requires c <= -52 && c >= -52
{
  assert (a + b) * c == a * c + b * c;
}
