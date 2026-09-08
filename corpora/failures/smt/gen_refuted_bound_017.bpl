procedure p_ref_bnd_17(x: int)
  requires 0 <= x && x <= 20
{
  assert x * x >= 21;
}
