// timeout family: Fermat n=5 shape. Proving the goal requires deciding the
// unsatisfiability of x^5+y^5==z^5 over positive integers - never fast for z3.
// Expected status is "timeout"/"open" (scheduler-dependent) but NEVER discharged
// or refuted within the corpus budget.
procedure fermat5(x: int, y: int, z: int)
  requires x >= 1 && y >= 1 && z >= 1
{
  assert x * x * x * x * x + y * y * y * y * y != z * z * z * z * z;
}
