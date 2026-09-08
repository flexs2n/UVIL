procedure p(x: int)
  requires x >= -416 && x <= 416
{
  assert (if x < 0 then -x else x) <= 416;
}
