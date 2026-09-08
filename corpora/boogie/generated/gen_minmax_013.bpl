procedure p(a: int, b: int)
  requires a <= 563 && b <= 417
{
  assert (if a < b then a else b) <= 563;
}
