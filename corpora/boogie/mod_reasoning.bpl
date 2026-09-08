// mod reasoning family
procedure mod_self(a: int, b: int)
  requires b == 3
{
  assert (a + b) % b == a % b;
}

procedure mod_double(a: int, b: int)
  requires b > 0
{
  assert (2 * a) % b == (a + a) % b;
}
