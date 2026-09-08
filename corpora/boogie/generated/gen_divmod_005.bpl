procedure p(a: int, b: int)
  requires b == 181
{
  assert a / b * b + a % b == a;
}
