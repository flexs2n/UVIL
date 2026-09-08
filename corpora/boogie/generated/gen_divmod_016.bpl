procedure p(a: int, b: int)
  requires b == 61
{
  assert a / b * b + a % b == a;
}
