procedure p_ref_bnd_5(x: int)
  requires 0 <= x && x <= 8
{
  assert x * x >= 9;
}
