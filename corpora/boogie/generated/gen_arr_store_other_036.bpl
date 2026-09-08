procedure p(a: [int]int)
  requires 86 != 10
{
  assert a[86 := 61][10] == a[10];
}
