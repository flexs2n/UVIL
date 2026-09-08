function f_5(x: int) returns (int);
procedure p_uninterp_5(x: int)
{
  assert f_5(x) >= 5;
}
