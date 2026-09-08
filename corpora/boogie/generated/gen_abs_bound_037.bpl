procedure p(x: int)
  requires x >= -86 && x <= 86
{
  assert (if x < 0 then -x else x) <= 86;
}
