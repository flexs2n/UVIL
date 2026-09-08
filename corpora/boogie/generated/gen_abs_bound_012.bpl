procedure p(x: int)
  requires x >= -394 && x <= 394
{
  assert (if x < 0 then -x else x) <= 394;
}
