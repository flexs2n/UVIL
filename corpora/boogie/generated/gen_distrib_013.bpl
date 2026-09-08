procedure p(a: int, b: int, c: int)
  requires c <= -21 && c >= -21
{
  assert (a + b) * c == a * c + b * c;
}
