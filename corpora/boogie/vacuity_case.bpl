// intentional vacuity case: contradictory preconditions make any goal provable.
// M1 honestly reports "discharged" here; vacuity detection via shadow sets is
// M2 work (draft R4). The corpus pins today's semantics.
procedure vacuous(x: int)
  requires x >= 0
  requires x < 0
{
  assert x == 1000000;
}
