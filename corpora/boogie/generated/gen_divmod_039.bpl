procedure p(a: int, b: int)
  requires b == 92
{
  assert a / b * b + a % b == a;
}
