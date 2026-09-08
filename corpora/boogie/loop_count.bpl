// loop-invariant count family
procedure loop_count(n: int)
  requires n >= 0
{
  var k: int;
  assume k == 0;
  while k != n
    invariant k >= 0
  {
    k := k + 1;
  }
  assert k >= 0;
}
