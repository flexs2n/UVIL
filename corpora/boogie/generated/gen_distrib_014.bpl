procedure p(a: int, b: int, c: int)
  requires c <= -29 && c >= -29
{
  assert (a + b) * c == a * c + b * c;
}
