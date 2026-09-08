procedure p(a: [int]int)
  requires 39 != 61
{
  assert a[39 := 23][61] == a[61];
}
