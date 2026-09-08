procedure p(a: [int]int)
  requires 39 != 49
{
  assert a[39 := 22][49] == a[49];
}
