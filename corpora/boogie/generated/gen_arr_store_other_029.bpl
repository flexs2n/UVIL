procedure p(a: [int]int)
  requires 4 != 36
{
  assert a[4 := 4][36] == a[36];
}
