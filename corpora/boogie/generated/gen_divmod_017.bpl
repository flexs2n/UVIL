procedure p(a: int, b: int)
  requires b == 40
{
  assert a / b * b + a % b == a;
}
