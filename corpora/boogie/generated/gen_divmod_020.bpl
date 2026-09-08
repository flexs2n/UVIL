procedure p(a: int, b: int)
  requires b == 51
{
  assert a / b * b + a % b == a;
}
