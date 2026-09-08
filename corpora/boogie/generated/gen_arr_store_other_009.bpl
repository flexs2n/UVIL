procedure p(a: [int]int)
  requires 22 != 47
{
  assert a[22 := 40][47] == a[47];
}
