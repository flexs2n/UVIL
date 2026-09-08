procedure p(a: [int]int, n: int)
  requires n >= 22
  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0
{
  assert a[22 - 1] >= 0;
}
