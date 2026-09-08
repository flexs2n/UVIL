procedure p_ref_bnd_24(x: int)
  requires 0 <= x && x <= 27
{
  assert x * x >= 28;
}
