procedure p(a: int, b: int)
  requires b == 152
{
  assert a / b * b + a % b == a;
}
