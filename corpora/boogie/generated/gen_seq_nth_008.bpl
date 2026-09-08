procedure p(s: seq<int>)
  requires |s| > 19
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[19] >= 0 && |s| >= 1;
}
