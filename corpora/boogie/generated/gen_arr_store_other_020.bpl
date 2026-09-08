procedure p(a: [int]int)
  requires 61 != 74
{
  assert a[61 := 35][74] == a[74];
}
