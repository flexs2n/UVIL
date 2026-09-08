procedure p(a: int, b: int, c: int)
  requires c <= 53 && c >= 53
{
  assert (a + b) * c == a * c + b * c;
}
