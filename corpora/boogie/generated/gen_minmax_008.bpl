procedure p(a: int, b: int)
  requires a <= 301 && b <= 404
{
  assert (if a < b then a else b) <= 404;
}
