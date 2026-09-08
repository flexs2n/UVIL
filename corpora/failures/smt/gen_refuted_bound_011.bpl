procedure p_ref_bnd_11(x: int)
  requires 0 <= x && x <= 14
{
  assert x * x >= 15;
}
