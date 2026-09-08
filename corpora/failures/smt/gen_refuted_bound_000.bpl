procedure p_ref_bnd_0(x: int)
  requires 0 <= x && x <= 3
{
  assert x * x >= 4;
}
