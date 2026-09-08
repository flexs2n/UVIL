procedure p(a: [int]int)
  requires 75 != 85
{
  assert a[75 := 32][85] == a[85];
}
