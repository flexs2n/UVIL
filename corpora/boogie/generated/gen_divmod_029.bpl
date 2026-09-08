procedure p(a: int, b: int)
  requires b == 36
{
  assert a / b * b + a % b == a;
}
