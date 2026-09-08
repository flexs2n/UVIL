procedure p(a: [int]int)
  requires 45 != 65
{
  assert a[45 := 82][65] == a[65];
}
