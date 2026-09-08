procedure loop_sum_20(n: int)
  requires n >= 60
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
