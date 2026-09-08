procedure p(a: int, b: int, c: int)
  requires c <= -45 && c >= -45
{
  assert (a + b) * c == a * c + b * c;
}
