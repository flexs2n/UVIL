procedure p(s: seq<int>)
  requires |s| > 58
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[58] >= 0 && |s| >= 1;
}
