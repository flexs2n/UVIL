procedure p(a: [int]int, n: int)
  requires n >= 28
  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0
{
  assert a[28 - 1] >= 0;
}
