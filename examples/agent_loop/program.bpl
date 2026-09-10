// The agent-loop repair target (WI-4 demo).
procedure clamp_ok(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  assert y >= -k && y <= k;
}

procedure clamp_step(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  y := y + 1;
  assert y <= k;
}
