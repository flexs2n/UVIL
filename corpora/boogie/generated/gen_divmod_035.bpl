procedure p(a: int, b: int)
  requires b == 136
{
  assert a / b * b + a % b == a;
}
