procedure p(a: [int]int)
  requires 84 != 22
{
  assert a[84 := 32][22] == a[22];
}
