procedure p(a: int, b: int)
  requires b == 108
{
  assert a / b * b + a % b == a;
}
