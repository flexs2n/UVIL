procedure p_ref_lin_31(a: int)
  requires a >= 32
{
  assert a + a == 3 * a;
}
