procedure p(a: [int]int)
  requires 69 != 1
{
  assert a[69 := 11][1] == a[1];
}
