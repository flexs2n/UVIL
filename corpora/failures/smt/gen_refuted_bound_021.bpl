procedure p_ref_bnd_21(x: int)
  requires 0 <= x && x <= 24
{
  assert x * x >= 25;
}
