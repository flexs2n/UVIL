procedure p(a: int, b: int)
  requires b == 7
{
  assert a / b * b + a % b == a;
}
