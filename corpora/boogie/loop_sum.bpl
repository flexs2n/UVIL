// loop-invariant sum family (WP VCG: initiation/preservation/assert obligations)
procedure loop_sum(n: int)
  requires n >= 1
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
