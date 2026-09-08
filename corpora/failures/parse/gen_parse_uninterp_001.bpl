function f_1(x: int) returns (int);
procedure p_uninterp_1(x: int)
{
  assert f_1(x) >= 1;
}
