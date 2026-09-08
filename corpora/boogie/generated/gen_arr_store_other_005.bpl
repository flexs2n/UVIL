procedure p(a: [int]int)
  requires 76 != 74
{
  assert a[76 := 63][74] == a[74];
}
