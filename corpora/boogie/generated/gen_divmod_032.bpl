procedure p(a: int, b: int)
  requires b == 172
{
  assert a / b * b + a % b == a;
}
