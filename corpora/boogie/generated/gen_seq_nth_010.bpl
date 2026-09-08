procedure p(s: seq<int>)
  requires |s| > 36
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[36] >= 0 && |s| >= 1;
}
