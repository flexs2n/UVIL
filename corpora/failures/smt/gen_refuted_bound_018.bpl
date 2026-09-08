procedure p_ref_bnd_18(x: int)
  requires 0 <= x && x <= 21
{
  assert x * x >= 22;
}
