procedure p(a: int, b: int)
  requires b == 73
{
  assert a / b * b + a % b == a;
}
