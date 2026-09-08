procedure p(a: [int]int)
  requires 66 != 65
{
  assert a[66 := 17][65] == a[65];
}
