// array bounds via select + quantified assumption
procedure bounds(a: [int]int, n: int)
  requires n >= 1
  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0
{
  assert a[n - 1] >= 0;
}
