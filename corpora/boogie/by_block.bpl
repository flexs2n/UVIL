// assert ... by blocks: block assumes join the context
procedure by_block(x: int)
  requires x >= 5
{
  assert x >= 1 by {
    assume x >= 0;
  }
}
