procedure p_ref_bnd_27(x: int)
  requires 0 <= x && x <= 30
{
  assert x * x >= 31;
}
