// map store/select family
procedure store_other(a: [int]int, i: int, j: int, v: int)
  requires i != j
{
  assert a[i := v][j] == a[j];
}

procedure store_same(a: [int]int)
{
  assert a[3 := 42][3] == 42;
}
