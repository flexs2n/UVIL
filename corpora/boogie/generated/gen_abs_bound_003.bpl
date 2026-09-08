procedure p(x: int)
  requires x >= -46 && x <= 46
{
  assert (if x < 0 then -x else x) <= 46;
}
