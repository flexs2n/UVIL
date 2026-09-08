procedure p(a: [int]int)
  requires 67 != 55
{
  assert a[67 := 44][55] == a[55];
}
