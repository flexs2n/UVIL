procedure p(x: int)
  requires x >= -320 && x <= 320
{
  assert (if x < 0 then -x else x) <= 320;
}
