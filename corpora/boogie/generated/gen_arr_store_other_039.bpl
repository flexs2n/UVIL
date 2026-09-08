procedure p(a: [int]int)
  requires 75 != 12
{
  assert a[75 := 66][12] == a[12];
}
