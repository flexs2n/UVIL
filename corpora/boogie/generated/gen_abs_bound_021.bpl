procedure p(x: int)
  requires x >= -469 && x <= 469
{
  assert (if x < 0 then -x else x) <= 469;
}
