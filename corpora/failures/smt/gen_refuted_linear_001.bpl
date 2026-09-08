procedure p_ref_lin_1(a: int)
  requires a >= 2
{
  assert a + a == 3 * a;
}
