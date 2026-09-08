procedure p(a: [int]int)
  requires 28 != 76
{
  assert a[28 := 22][76] == a[76];
}
