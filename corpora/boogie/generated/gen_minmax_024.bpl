procedure p(a: int, b: int)
  requires a <= 390 && b <= 368
{
  assert (if a < b then a else b) <= 390;
}
