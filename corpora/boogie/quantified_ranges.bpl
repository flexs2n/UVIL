// quantified ranges over integers
procedure range_nonneg(n: int)
  requires n >= 1
  requires forall i: int :: 0 <= i && i < n ==> i <= n
{
  assert forall j: int :: 0 <= j && j < n ==> j < n + 1;
}

procedure range_sum_bound(n: int)
  requires n >= 0
  requires forall i: int :: 0 <= i && i < n ==> i < n
{
  assert forall k: int :: k >= n ==> k >= 0;
}
