procedure p(x: int)
  requires x >= -152 && x <= 152
{
  assert (if x < 0 then -x else x) <= 152;
}
