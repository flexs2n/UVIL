procedure p(a: [int]int)
  requires 59 != 80
{
  assert a[59 := 25][80] == a[80];
}
