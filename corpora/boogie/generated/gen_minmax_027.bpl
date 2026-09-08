procedure p(a: int, b: int)
  requires a <= 382 && b <= 418
{
  assert (if a < b then a else b) <= 418;
}
