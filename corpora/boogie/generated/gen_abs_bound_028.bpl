procedure p(x: int)
  requires x >= -483 && x <= 483
{
  assert (if x < 0 then -x else x) <= 483;
}
