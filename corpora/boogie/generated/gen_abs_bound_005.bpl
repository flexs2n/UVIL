procedure p(x: int)
  requires x >= -393 && x <= 393
{
  assert (if x < 0 then -x else x) <= 393;
}
