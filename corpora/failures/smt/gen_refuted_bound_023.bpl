procedure p_ref_bnd_23(x: int)
  requires 0 <= x && x <= 26
{
  assert x * x >= 27;
}
