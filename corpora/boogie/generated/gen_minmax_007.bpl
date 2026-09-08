procedure p(a: int, b: int)
  requires a <= 469 && b <= 313
{
  assert (if a < b then a else b) <= 469;
}
