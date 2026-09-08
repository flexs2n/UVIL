procedure p(x: int)
  requires x >= -300 && x <= 300
{
  assert (if x < 0 then -x else x) <= 300;
}
