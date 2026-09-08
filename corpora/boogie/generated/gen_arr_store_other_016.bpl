procedure p(a: [int]int)
  requires 78 != 5
{
  assert a[78 := 25][5] == a[5];
}
