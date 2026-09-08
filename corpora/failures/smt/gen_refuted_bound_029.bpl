procedure p_ref_bnd_29(x: int)
  requires 0 <= x && x <= 32
{
  assert x * x >= 33;
}
