procedure p(a: int, b: int)
  requires a <= 378 && b <= 273
{
  assert (if a < b then a else b) <= 378;
}
