procedure p(a: int, b: int, c: int)
  requires c <= -41 && c >= -41
{
  assert (a + b) * c == a * c + b * c;
}
