// churn scenario (fixed-seed LIA families)
procedure p0(x: int)
  requires x >= 3
{
  assert x + 0 == x;
}

procedure p1(x: int, y: int)
  requires x >= 4 && y >= 4
{
  assert x + y == y + x;
}

procedure p2(x: int)
  requires 0 <= x && x <= 5
{
  assert x + x >= 0;
}

procedure p3(a: int, b: int)
  requires b == 3
{
  assert (a + b) % b == a % b;
}
