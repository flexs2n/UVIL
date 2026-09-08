procedure p(s: seq<int>)
  requires |s| > 57
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[57] >= 0 && |s| >= 1;
}
