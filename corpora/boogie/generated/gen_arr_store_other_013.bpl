procedure p(a: [int]int)
  requires 32 != 34
{
  assert a[32 := 17][34] == a[34];
}
