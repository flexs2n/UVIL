procedure p(a: [int]int)
  requires 44 != 56
{
  assert a[44 := 40][56] == a[56];
}
