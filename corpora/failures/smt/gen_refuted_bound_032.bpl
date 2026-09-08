procedure p_ref_bnd_32(x: int)
  requires 0 <= x && x <= 35
{
  assert x * x >= 36;
}
