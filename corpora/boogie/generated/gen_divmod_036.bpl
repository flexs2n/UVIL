procedure p(a: int, b: int)
  requires b == 82
{
  assert a / b * b + a % b == a;
}
