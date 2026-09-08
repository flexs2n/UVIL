procedure p_ref_bnd_1(x: int)
  requires 0 <= x && x <= 4
{
  assert x * x >= 5;
}
