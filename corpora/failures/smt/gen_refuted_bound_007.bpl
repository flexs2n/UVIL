procedure p_ref_bnd_7(x: int)
  requires 0 <= x && x <= 10
{
  assert x * x >= 11;
}
