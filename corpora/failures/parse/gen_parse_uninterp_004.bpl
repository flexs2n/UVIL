function f_4(x: int) returns (int);
procedure p_uninterp_4(x: int)
{
  assert f_4(x) >= 4;
}
