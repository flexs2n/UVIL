procedure p(a: [int]int)
  requires 76 != 5
{
  assert a[76 := 43][5] == a[5];
}
