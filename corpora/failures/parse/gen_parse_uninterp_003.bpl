function f_3(x: int) returns (int);
procedure p_uninterp_3(x: int)
{
  assert f_3(x) >= 3;
}
