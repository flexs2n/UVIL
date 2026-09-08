procedure p(a: int, b: int, c: int)
  requires c <= -33 && c >= -33
{
  assert (a + b) * c == a * c + b * c;
}
