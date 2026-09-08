procedure p(a: int, b: int)
  requires b == 26
{
  assert a / b * b + a % b == a;
}
