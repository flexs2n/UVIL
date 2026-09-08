procedure p(x: int)
  requires x >= -443 && x <= 443
{
  assert (if x < 0 then -x else x) <= 443;
}
