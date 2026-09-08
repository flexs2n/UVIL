procedure p(x: int)
  requires x >= -296 && x <= 296
{
  assert (if x < 0 then -x else x) <= 296;
}
