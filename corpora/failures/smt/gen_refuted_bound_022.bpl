procedure p_ref_bnd_22(x: int)
  requires 0 <= x && x <= 25
{
  assert x * x >= 26;
}
