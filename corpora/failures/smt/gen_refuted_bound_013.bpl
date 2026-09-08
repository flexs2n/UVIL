procedure p_ref_bnd_13(x: int)
  requires 0 <= x && x <= 16
{
  assert x * x >= 17;
}
