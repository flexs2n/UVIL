procedure p(a: [int]int)
  requires 57 != 42
{
  assert a[57 := 67][42] == a[42];
}
