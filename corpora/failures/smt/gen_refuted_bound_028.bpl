procedure p_ref_bnd_28(x: int)
  requires 0 <= x && x <= 31
{
  assert x * x >= 32;
}
