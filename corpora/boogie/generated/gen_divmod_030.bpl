procedure p(a: int, b: int)
  requires b == 98
{
  assert a / b * b + a % b == a;
}
