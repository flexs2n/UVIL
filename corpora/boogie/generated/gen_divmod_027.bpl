procedure p(a: int, b: int)
  requires b == 142
{
  assert a / b * b + a % b == a;
}
