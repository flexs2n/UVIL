procedure p(s: seq<int>)
  requires |s| > 46
  requires forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0
{
  assert s[46] >= 0 && |s| >= 1;
}
