// Dafny twin of vec_push.bpl: same contract, different home format.
// Requires Dafny at the pinned version (ADR 0002); the CLI path skips cleanly
// when Dafny is absent.
method VecPush(len: int, cap: int) returns (len': int)
  requires len < cap
  ensures len' == len + 1
{
  len' := len + 1;
  assert len' <= cap;
}
