procedure p(x: int)
  requires x >= -408 && x <= 408
{
  assert (if x < 0 then -x else x) <= 408;
}
