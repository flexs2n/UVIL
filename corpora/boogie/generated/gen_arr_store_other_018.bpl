procedure p(a: [int]int)
  requires 41 != 43
{
  assert a[41 := 29][43] == a[43];
}
