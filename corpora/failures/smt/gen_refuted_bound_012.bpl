procedure p_ref_bnd_12(x: int)
  requires 0 <= x && x <= 15
{
  assert x * x >= 16;
}
