procedure p(a: int, b: int)
  requires a <= 256 && b <= 382
{
  assert (if a < b then a else b) <= 382;
}
