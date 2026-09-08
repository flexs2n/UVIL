procedure p(a: int, b: int)
  requires b == 67
{
  assert a / b * b + a % b == a;
}
