procedure p(a: int)
  requires a >= 63
{
  assert a + a == 3 * a;
}
