procedure p(a: int, b: int)
  requires b == 95
{
  assert a / b * b + a % b == a;
}
