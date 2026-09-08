// sequence operations family (seq.nth / seq.len; seq.update has no SMT-LIB
// rendering in z3 5.1.0 and is left to the fail-loud opaque path)
procedure seq_len(s: seq<int>)
  requires |s| > 0
{
  assert |s| >= 1;
}

procedure seq_nth_nonneg(s: seq<int>)
  requires |s| > 2
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[1] >= 0;
}

procedure seq_len_mono(s: seq<int>)
{
  assert |s| >= 0;
}
