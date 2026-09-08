// arithmetic identities family
procedure add_comm(a: int, b: int)
  requires a >= -50 && b >= -50
{
  assert a + b == b + a;
}

procedure add_comm3(a: int, b: int, c: int)
  requires a >= 0 && b >= 0 && c >= 0
{
  assert a + b + c == c + b + a;
}

procedure mul_comm(a: int, b: int)
  requires a <= 10 && b <= 10
{
  assert a * b == b * a;
}
