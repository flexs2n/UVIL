procedure p(x: int)
  requires x >= -485 && x <= 485
{
  assert (if x < 0 then -x else x) <= 485;
}
