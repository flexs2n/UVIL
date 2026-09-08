function f_2(x: int) returns (int);
procedure p_uninterp_2(x: int)
{
  assert f_2(x) >= 2;
}
