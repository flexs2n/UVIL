procedure p_ref_bnd_38(x: int)
  requires 0 <= x && x <= 41
{
  assert x * x >= 42;
}
