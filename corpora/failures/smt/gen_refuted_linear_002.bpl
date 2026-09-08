procedure p_ref_lin_2(a: int)
  requires a >= 3
{
  assert a + a == 3 * a;
}
