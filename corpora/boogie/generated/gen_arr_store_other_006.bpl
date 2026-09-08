procedure p(a: [int]int)
  requires 47 != 78
{
  assert a[47 := 15][78] == a[78];
}
