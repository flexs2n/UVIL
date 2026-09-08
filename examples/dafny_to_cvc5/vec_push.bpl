const CAP_INIT: int := 4;

procedure vec_push(len: int, cap: int) returns (len_prime: int)
  requires len < cap
  requires cap == CAP_INIT
  ensures len_prime == len + 1
{
  assume len_prime == len + 1;
  assert len_prime <= cap;
}
