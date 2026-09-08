procedure p(a: [int]int)
  requires 41 != 2
{
  assert a[41 := 50][2] == a[2];
}
