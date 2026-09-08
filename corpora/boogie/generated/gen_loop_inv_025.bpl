procedure loop_sum_25(n: int)
  requires n >= 11
{
  var i: int;
  assume i == 0;
  while i < n
    invariant i >= 0
  {
    i := i + 1;
  }
  assert i >= 0;
}
