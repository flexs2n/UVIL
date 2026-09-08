procedure p(a: [int]int)
  requires 33 != 67
{
  assert a[33 := 46][67] == a[67];
}
