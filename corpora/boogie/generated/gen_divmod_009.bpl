procedure p(a: int, b: int)
  requires b == 111
{
  assert a / b * b + a % b == a;
}
