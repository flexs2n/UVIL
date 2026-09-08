procedure p(x: int)
  requires x >= -95 && x <= 95
{
  assert (if x < 0 then -x else x) <= 95;
}
