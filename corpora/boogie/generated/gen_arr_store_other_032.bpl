procedure p(a: [int]int)
  requires 26 != 34
{
  assert a[26 := 15][34] == a[34];
}
