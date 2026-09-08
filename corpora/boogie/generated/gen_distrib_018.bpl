procedure p(a: int, b: int, c: int)
  requires c <= -96 && c >= -96
{
  assert (a + b) * c == a * c + b * c;
}
