procedure p(a: [int]int)
  requires 15 != 47
{
  assert a[15 := 71][47] == a[47];
}
