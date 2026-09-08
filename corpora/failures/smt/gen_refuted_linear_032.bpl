procedure p_ref_lin_32(a: int)
  requires a >= 33
{
  assert a + a == 3 * a;
}
