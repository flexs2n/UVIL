procedure p(a: int, b: int)
  requires b == 53
{
  assert a / b * b + a % b == a;
}
