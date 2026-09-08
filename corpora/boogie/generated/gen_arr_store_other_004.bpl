procedure p(a: [int]int)
  requires 36 != 34
{
  assert a[36 := 14][34] == a[34];
}
