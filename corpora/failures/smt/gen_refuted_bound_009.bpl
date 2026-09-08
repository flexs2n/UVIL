procedure p_ref_bnd_9(x: int)
  requires 0 <= x && x <= 12
{
  assert x * x >= 13;
}
