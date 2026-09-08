// a too-weak invariant does not help: the goal is genuinely unprovable here
procedure loop_weaker(n: int)
  requires n >= 0
{
  var i: int;
  assume i == 0;
  while i < n
    invariant true
  {
    i := i + 1;
  }
  assert i == n;
}
