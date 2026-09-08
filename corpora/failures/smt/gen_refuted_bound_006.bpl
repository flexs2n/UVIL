procedure p_ref_bnd_6(x: int)
  requires 0 <= x && x <= 9
{
  assert x * x >= 10;
}
