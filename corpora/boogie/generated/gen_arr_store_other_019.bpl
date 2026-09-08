procedure p(a: [int]int)
  requires 65 != 57
{
  assert a[65 := 21][57] == a[57];
}
