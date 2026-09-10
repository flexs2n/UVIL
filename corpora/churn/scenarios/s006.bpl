// churn scenario (fixed-seed LIA families)
procedure p0(x: int)
  requires x >= 9
{
  assert x + 0 == x;
}

procedure p1(x: int, y: int)
  requires x >= 10 && y >= 10
{
  assert x + y == y + x;
}

procedure p2(x: int)
  requires 0 <= x && x <= 11
{
  assert x + x >= 0;
}

procedure p3(a: int, b: int)
  requires b == 3
{
  assert (a + b) % b == a % b;
}
