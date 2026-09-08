procedure p(a: [int]int)
  requires 69 != 89
{
  assert a[69 := 31][89] == a[89];
}
