procedure p(a: int, b: int)
  requires b == 30
{
  assert a / b * b + a % b == a;
}
