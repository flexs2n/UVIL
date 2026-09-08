procedure p(a: int, b: int)
  requires a <= 287 && b <= 271
{
  assert (if a < b then a else b) <= 287;
}
