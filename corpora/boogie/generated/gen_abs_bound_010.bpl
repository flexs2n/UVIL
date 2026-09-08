procedure p(x: int)
  requires x >= -439 && x <= 439
{
  assert (if x < 0 then -x else x) <= 439;
}
