procedure p(a: int, b: int)
  requires b == 176
{
  assert a / b * b + a % b == a;
}
