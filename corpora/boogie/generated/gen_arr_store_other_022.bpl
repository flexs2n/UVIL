procedure p(a: [int]int)
  requires 50 != 79
{
  assert a[50 := 69][79] == a[79];
}
