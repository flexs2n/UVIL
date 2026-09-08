procedure p(x: int)
  requires x >= -269 && x <= 269
{
  assert (if x < 0 then -x else x) <= 269;
}
