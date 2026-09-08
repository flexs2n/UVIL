function f_10(x: int) returns (int);
procedure p_uninterp_10(x: int)
{
  assert f_10(x) >= 10;
}
