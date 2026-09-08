procedure p_ref_bnd_30(x: int)
  requires 0 <= x && x <= 33
{
  assert x * x >= 34;
}
