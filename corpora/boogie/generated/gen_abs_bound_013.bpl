procedure p(x: int)
  requires x >= -77 && x <= 77
{
  assert (if x < 0 then -x else x) <= 77;
}
