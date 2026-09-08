procedure p(x: int)
  requires x >= -475 && x <= 475
{
  assert (if x < 0 then -x else x) <= 475;
}
