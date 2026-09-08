procedure p(a: int, b: int)
  requires b == 178
{
  assert a / b * b + a % b == a;
}
