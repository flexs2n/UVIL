procedure p(a: [int]int, n: int)
  requires n >= 7
  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0
{
  assert a[7 - 1] >= 0;
}
