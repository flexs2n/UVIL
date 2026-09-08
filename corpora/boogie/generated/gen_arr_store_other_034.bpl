procedure p(a: [int]int)
  requires 83 != 37
{
  assert a[83 := 54][37] == a[37];
}
