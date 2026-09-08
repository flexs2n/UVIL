procedure p(x: int)
  requires x >= -423 && x <= 423
{
  assert (if x < 0 then -x else x) <= 423;
}
