procedure p_ref_bnd_39(x: int)
  requires 0 <= x && x <= 42
{
  assert x * x >= 43;
}
