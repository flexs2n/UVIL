procedure p(a: [int]int)
  requires 42 != 32
{
  assert a[42 := 61][32] == a[32];
}
