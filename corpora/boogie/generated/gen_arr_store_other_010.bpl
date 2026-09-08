procedure p(a: [int]int)
  requires 60 != 69
{
  assert a[60 := 64][69] == a[69];
}
