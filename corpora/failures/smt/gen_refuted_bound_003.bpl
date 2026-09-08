procedure p_ref_bnd_3(x: int)
  requires 0 <= x && x <= 6
{
  assert x * x >= 7;
}
