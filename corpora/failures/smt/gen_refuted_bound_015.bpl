procedure p_ref_bnd_15(x: int)
  requires 0 <= x && x <= 18
{
  assert x * x >= 19;
}
