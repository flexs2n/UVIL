procedure p_ref_bnd_25(x: int)
  requires 0 <= x && x <= 28
{
  assert x * x >= 29;
}
