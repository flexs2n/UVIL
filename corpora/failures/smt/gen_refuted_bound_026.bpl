procedure p_ref_bnd_26(x: int)
  requires 0 <= x && x <= 29
{
  assert x * x >= 30;
}
