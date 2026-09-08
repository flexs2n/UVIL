procedure p(x: int)
  requires x >= -186 && x <= 186
{
  assert (if x < 0 then -x else x) <= 186;
}
