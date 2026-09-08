procedure p_ref_bnd_2(x: int)
  requires 0 <= x && x <= 5
{
  assert x * x >= 6;
}
