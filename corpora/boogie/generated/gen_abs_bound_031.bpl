procedure p(x: int)
  requires x >= -88 && x <= 88
{
  assert (if x < 0 then -x else x) <= 88;
}
