procedure p(s: seq<int>)
  requires |s| > 10
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[10] >= 0 && |s| >= 1;
}
