procedure p(a: [int]int)
  requires 19 != 61
{
  assert a[19 := 7][61] == a[61];
}
