procedure p(s: seq<int>)
  requires |s| > 16
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[16] >= 0 && |s| >= 1;
}
