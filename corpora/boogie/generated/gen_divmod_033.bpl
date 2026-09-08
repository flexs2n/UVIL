procedure p(a: int, b: int)
  requires b == 133
{
  assert a / b * b + a % b == a;
}
