procedure p(x: int)
  requires x >= -432 && x <= 432
{
  assert (if x < 0 then -x else x) <= 432;
}
