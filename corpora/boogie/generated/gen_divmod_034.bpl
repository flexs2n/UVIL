procedure p(a: int, b: int)
  requires b == 46
{
  assert a / b * b + a % b == a;
}
