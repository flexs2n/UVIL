procedure p(a: int, b: int)
  requires b == 68
{
  assert a / b * b + a % b == a;
}
