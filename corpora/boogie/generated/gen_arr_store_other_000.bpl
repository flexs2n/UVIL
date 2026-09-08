procedure p(a: [int]int)
  requires 67 != 16
{
  assert a[67 := 46][16] == a[16];
}
