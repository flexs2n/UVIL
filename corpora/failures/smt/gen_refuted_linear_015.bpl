procedure p_ref_lin_15(a: int)
  requires a >= 16
{
  assert a + a == 3 * a;
}
