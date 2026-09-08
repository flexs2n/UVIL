procedure p(a: int, b: int)
  requires a <= 381 && b <= 501
{
  assert (if a < b then a else b) <= 501;
}
