procedure p(a: int, b: int)
  requires b == 113
{
  assert a / b * b + a % b == a;
}
