// div/mod family (Euclidean semantics, positive divisor)
procedure divmod_identity(a: int, b: int)
  requires b > 0
{
  assert a / b * b + a % b == a;
}

procedure mod_range(a: int, b: int)
  requires b > 0
{
  assert a % b >= 0 && a % b < b;
}
