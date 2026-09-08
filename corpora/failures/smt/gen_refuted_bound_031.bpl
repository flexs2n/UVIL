procedure p_ref_bnd_31(x: int)
  requires 0 <= x && x <= 34
{
  assert x * x >= 35;
}
