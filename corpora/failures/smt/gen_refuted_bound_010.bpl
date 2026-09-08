procedure p_ref_bnd_10(x: int)
  requires 0 <= x && x <= 13
{
  assert x * x >= 14;
}
