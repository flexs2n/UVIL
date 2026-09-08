procedure p_ref_bnd_8(x: int)
  requires 0 <= x && x <= 11
{
  assert x * x >= 12;
}
