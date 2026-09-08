procedure p(x: int)
  requires x >= -181 && x <= 181
{
  assert (if x < 0 then -x else x) <= 181;
}
