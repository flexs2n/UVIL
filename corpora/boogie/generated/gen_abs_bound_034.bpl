procedure p(x: int)
  requires x >= -486 && x <= 486
{
  assert (if x < 0 then -x else x) <= 486;
}
