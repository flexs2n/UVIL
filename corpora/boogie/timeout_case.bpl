// timeout family: quintic Fermat shape; never decided within a small budget.
// Expected status is "timeout"/"open" (scheduler-dependent) but NEVER discharged.
procedure fermat5(x: int, y: int, z: int)
  requires x >= 1 && y >= 1 && z >= 1
{
  assert x * x * x * x * x + y * y * y * y * y == z * z * z * z * z;
}
