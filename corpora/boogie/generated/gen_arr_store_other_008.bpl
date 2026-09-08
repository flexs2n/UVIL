procedure p(a: [int]int)
  requires 69 != 37
{
  assert a[69 := 29][37] == a[37];
}
