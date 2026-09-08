// refutable bounded family: x*x < 7 has witnesses in [0, 5]
procedure small_square(x: int)
  requires 0 <= x && x <= 5
{
  assert x * x >= 7;
}
