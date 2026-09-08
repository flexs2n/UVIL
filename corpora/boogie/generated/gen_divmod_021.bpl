procedure p(a: int, b: int)
  requires b == 182
{
  assert a / b * b + a % b == a;
}
