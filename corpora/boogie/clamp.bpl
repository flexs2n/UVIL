// clamp family: clamping to [0, k] stays in range and is idempotent
procedure clamp_range(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  assert (if x < 0 then 0 else (if x > k then k else x)) <= k;
}

procedure clamp_low(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  assert (if x < 0 then 0 else (if x > k then k else x)) >= 0;
}
