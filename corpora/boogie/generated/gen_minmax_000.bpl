procedure p(a: int, b: int)
  requires a <= 204 && b <= 450
{
  assert (if a < b then a else b) <= 450;
}
