procedure p(a: [int]int)
  requires 26 != 45
{
  assert a[26 := 9][45] == a[45];
}
