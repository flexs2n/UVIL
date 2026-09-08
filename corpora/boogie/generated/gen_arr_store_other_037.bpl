procedure p(a: [int]int)
  requires 38 != 89
{
  assert a[38 := 86][89] == a[89];
}
