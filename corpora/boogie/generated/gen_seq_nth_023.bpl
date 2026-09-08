procedure p(s: seq<int>)
  requires |s| > 47
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[47] >= 0 && |s| >= 0;
}
