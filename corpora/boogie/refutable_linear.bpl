// refutable linear family: the negation has a witness
procedure refutes(a: int)
  requires a >= 3
{
  assert a + a == 3 * a;
}
