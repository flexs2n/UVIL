procedure p(a: int, b: int)
  requires b == 63
{
  assert a / b * b + a % b == a;
}
