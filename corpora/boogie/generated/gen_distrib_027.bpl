procedure p(a: int, b: int, c: int)
  requires c <= -57 && c >= -57
{
  assert (a + b) * c == a * c + b * c;
}
