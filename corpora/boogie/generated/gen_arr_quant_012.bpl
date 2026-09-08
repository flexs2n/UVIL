procedure p(a: [int]int, n: int)
  requires n >= 30
  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0
{
  assert a[30 - 1] >= 0;
}
