procedure p(x: int)
  requires x >= -19 && x <= 19
{
  assert (if x < 0 then -x else x) <= 19;
}
