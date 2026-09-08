procedure p(a: int, b: int)
  requires b == 54
{
  assert a / b * b + a % b == a;
}
