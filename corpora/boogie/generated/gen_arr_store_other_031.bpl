procedure p(a: [int]int)
  requires 17 != 88
{
  assert a[17 := 74][88] == a[88];
}
