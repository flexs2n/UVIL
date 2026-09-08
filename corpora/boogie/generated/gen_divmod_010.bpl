procedure p(a: int, b: int)
  requires b == 186
{
  assert a / b * b + a % b == a;
}
