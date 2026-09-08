procedure p(a: int, b: int)
  requires b == 97
{
  assert a / b * b + a % b == a;
}
