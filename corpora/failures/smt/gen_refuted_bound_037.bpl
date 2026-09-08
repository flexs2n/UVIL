procedure p_ref_bnd_37(x: int)
  requires 0 <= x && x <= 40
{
  assert x * x >= 41;
}
