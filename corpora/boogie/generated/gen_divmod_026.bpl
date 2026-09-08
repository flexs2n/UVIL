procedure p(a: int, b: int)
  requires b == 141
{
  assert a / b * b + a % b == a;
}
