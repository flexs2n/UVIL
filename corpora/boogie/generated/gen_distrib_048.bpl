procedure p(a: int, b: int, c: int)
  requires c <= 51 && c >= 51
{
  assert (a + b) * c == a * c + b * c;
}
