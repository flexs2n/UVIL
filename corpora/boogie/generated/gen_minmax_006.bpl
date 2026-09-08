procedure p(a: int, b: int)
  requires a <= 378 && b <= 270
{
  assert (if a < b then a else b) <= 378;
}
