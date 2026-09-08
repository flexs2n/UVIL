procedure p(x: int)
  requires x >= -68 && x <= 68
{
  assert (if x < 0 then -x else x) <= 68;
}
