procedure p(s: seq<int>)
  requires |s| > 17
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[17] >= 0 && |s| >= 1;
}
