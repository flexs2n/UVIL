procedure p(x: int)
  requires x >= -499 && x <= 499
{
  assert (if x < 0 then -x else x) <= 499;
}
