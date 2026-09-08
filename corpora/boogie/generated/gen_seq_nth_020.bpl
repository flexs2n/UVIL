procedure p(s: seq<int>)
  requires |s| > 40
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[40] >= 0 && |s| >= 1;
}
