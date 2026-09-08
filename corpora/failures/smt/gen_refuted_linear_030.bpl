procedure p_ref_lin_30(a: int)
  requires a >= 31
{
  assert a + a == 3 * a;
}
