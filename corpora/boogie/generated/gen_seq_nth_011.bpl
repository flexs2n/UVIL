procedure p(s: seq<int>)
  requires |s| > 3
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[3] >= 0 && |s| >= 1;
}
