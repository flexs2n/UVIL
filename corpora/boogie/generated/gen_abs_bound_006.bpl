procedure p(x: int)
  requires x >= -51 && x <= 51
{
  assert (if x < 0 then -x else x) <= 51;
}
