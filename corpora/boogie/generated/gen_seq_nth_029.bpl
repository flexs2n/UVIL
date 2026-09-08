procedure p(s: seq<int>)
  requires |s| > 34
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[34] >= 0 && |s| >= 0;
}
