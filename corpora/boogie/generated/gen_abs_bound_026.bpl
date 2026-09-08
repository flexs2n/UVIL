procedure p(x: int)
  requires x >= -113 && x <= 113
{
  assert (if x < 0 then -x else x) <= 113;
}
