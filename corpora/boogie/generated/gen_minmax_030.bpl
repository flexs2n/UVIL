procedure p(a: int, b: int)
  requires a <= 542 && b <= 345
{
  assert (if a < b then a else b) <= 542;
}
