procedure p(a: int, b: int)
  requires a <= 558 && b <= 498
{
  assert (if a < b then a else b) <= 558;
}
