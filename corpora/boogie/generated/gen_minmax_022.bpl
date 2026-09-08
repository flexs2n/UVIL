procedure p(a: int, b: int)
  requires a <= 216 && b <= 215
{
  assert (if a < b then a else b) <= 216;
}
